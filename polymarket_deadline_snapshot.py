#!/usr/bin/env python3
"""Reusable snapshot and chart workflow for Polymarket deadline events."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

from plot_wti_timeseries import latest_window, load_ranges, load_snapshot
from polymarket_wti_snapshot import (
    all_markets_closed,
    build_session,
    collect_rows_and_ranges,
    fetch_event,
    merge_and_write_csv,
    merge_and_write_range_csv,
    market_is_closed,
    missing_range_targets,
    missing_snapshot_targets,
    range_output_for_snapshot,
    snapshot_targets,
    stored_snapshot_dates,
    TrackerResult,
)


LABEL_COLUMN = "Deadline"
LINE_CHART_LIMIT = 8


def load_resolution_probabilities(
    path: Path,
    *,
    event_key: str,
) -> dict[str, float]:
    """Load final Yes probabilities for resolved markets in one event."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        required = {"Event Key", "Market", "Current Status"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Resolution status CSV has an incompatible schema")
        probabilities: dict[str, float] = {}
        for row in reader:
            if str(row.get("Event Key") or "").strip() != event_key:
                continue
            if str(row.get("Current Status") or "").strip().lower() != "resolved":
                continue
            raw_value = str(row.get("Yes Resolution Probability") or "").strip()
            if not raw_value:
                continue
            value = float(raw_value)
            if not 0 <= value <= 100:
                raise ValueError("Resolved Yes probability must be between 0 and 100")
            probabilities[str(row.get("Market") or "").strip()] = value
    return probabilities


def load_closed_dates(
    path: Path,
    *,
    event_key: str,
) -> dict[str, str]:
    """Load the first detected closure date for each logical market."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        required = {
            "Detected At",
            "Event Key",
            "Market Label",
            "Event Type",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Market lifecycle CSV has an incompatible schema")
        closed_dates: dict[str, str] = {}
        for row in reader:
            if str(row.get("Event Key") or "").strip() != event_key:
                continue
            if str(row.get("Event Type") or "").strip().lower() != "closed":
                continue
            label = str(row.get("Market Label") or "").strip()
            detected_at = str(row.get("Detected At") or "").strip()
            try:
                detected_date = datetime.fromisoformat(
                    detected_at.replace("Z", "+00:00")
                ).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            except ValueError as exc:
                raise ValueError(f"Invalid lifecycle timestamp: {detected_at}") from exc
            if label and (
                label not in closed_dates or detected_date < closed_dates[label]
            ):
                closed_dates[label] = detected_date
    return closed_dates


def load_resolution_events(
    path: Path,
    *,
    event_key: str,
) -> list[dict[str, str]]:
    """Load timestamped dispute/resolution events for one chart."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        required = {"Observed At", "Event Key", "Market", "Event Type"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Resolution events CSV has an incompatible schema")
        events: list[dict[str, str]] = []
        for row in reader:
            if str(row.get("Event Key") or "").strip() != event_key:
                continue
            observed_at = str(row.get("Observed At") or "").strip()
            try:
                observed_date = datetime.fromisoformat(
                    observed_at.replace("Z", "+00:00")
                ).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            except ValueError as exc:
                raise ValueError(f"Invalid resolution-event timestamp: {observed_at}") from exc
            events.append(
                {
                    **{key: str(value or "") for key, value in row.items()},
                    "Observed Date": observed_date,
                }
            )
    return events


def apply_terminal_resolutions(
    dates: list[str],
    series: dict[str, list[float | None]],
    *,
    probabilities: dict[str, float],
    closed_dates: dict[str, str],
) -> tuple[list[str], dict[str, list[float | None]], dict[str, list[bool]]]:
    """Add derived terminal points without changing the raw snapshot CSV."""
    resolution_dates = [
        closed_dates[label]
        for label in probabilities
        if label in series and label in closed_dates
    ]
    combined_dates = sorted(set(dates + resolution_dates))
    date_indices = {date_string: index for index, date_string in enumerate(dates)}
    filled: dict[str, list[float | None]] = {}
    carried: dict[str, list[bool]] = {}
    for label, source_values in series.items():
        values: list[float | None] = []
        flags: list[bool] = []
        resolved_on = closed_dates.get(label)
        terminal = probabilities.get(label)
        for date_string in combined_dates:
            source_index = date_indices.get(date_string)
            value = source_values[source_index] if source_index is not None else None
            is_derived = (
                value is None
                and terminal is not None
                and resolved_on is not None
                and date_string >= resolved_on
            )
            values.append(terminal if is_derived else value)
            flags.append(is_derived)
        filled[label] = values
        carried[label] = flags
    return combined_dates, filled, carried


def selected_markets(
    markets: Iterable[dict[str, Any]], *, include_closed: bool = False
) -> list[dict[str, Any]]:
    """Return unresolved event markets unless closed markets were requested."""
    return [
        market
        for market in markets
        if include_closed or not market_is_closed(market)
    ]


def deadline_sort_key(label: str) -> tuple[int, int, str]:
    """Sort labels such as 'July 31' in calendar order."""
    try:
        parsed = datetime.strptime(label, "%B %d")
    except ValueError:
        return (13, 32, label)
    return (parsed.month, parsed.day, label)


def create_line_chart(
    dates: list[str],
    series: dict[str, list[float | None]],
    title: str,
    ranges: dict[str, dict[str, tuple[float | None, float | None]]] | None = None,
    carried_forward: dict[str, list[bool]] | None = None,
) -> Any:
    """Build a comparison line chart for a small set of deadline markets."""
    import plotly.graph_objects as go

    labels = sorted(series, key=deadline_sort_key)
    colors = [
        "#2563EB",
        "#0891B2",
        "#D97706",
        "#7C3AED",
        "#DC2626",
        "#059669",
        "#DB2777",
        "#4F46E5",
    ]
    figure = go.Figure()
    for index, label in enumerate(labels):
        color = colors[index % len(colors)]
        label_ranges = (ranges or {}).get(label, {})
        range_values = [label_ranges.get(date_string, (None, None)) for date_string in dates]
        carried_flags = (carried_forward or {}).get(label, [False] * len(dates))
        lower_errors: list[float | None] = []
        upper_errors: list[float | None] = []
        customdata: list[list[str]] = []
        statuses: list[str] = []
        for value, (low, high), is_carried in zip(
            series[label], range_values, carried_flags
        ):
            if is_carried and value is not None:
                low = high = value
            valid = (
                value is not None
                and low is not None
                and high is not None
                and low <= value <= high
            )
            lower_errors.append(value - low if valid else None)
            upper_errors.append(high - value if valid else None)
            customdata.append(
                [
                    "n/a" if not valid else f"{low:.1f}%",
                    "n/a" if not valid else f"{high:.1f}%",
                    (
                        "Resolved result carried forward"
                        if is_carried
                        else "Observed 9:00 AM snapshot"
                    ),
                ]
            )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=series[label],
                mode="lines+markers+text",
                name=label,
                connectgaps=False,
                line={"color": color, "width": 3},
                marker={"color": color, "size": 8},
                text=[
                    None if value is None else f"{value:.1f}%"
                    for value in series[label]
                ],
                textposition="top center",
                customdata=customdata,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": upper_errors,
                    "arrayminus": lower_errors,
                    "color": color,
                    "thickness": 2,
                    "width": 7,
                    "visible": any(value is not None for value in upper_errors),
                },
                hovertemplate=(
                    f"<b>{label}</b><br>%{{x}} at 9:00 AM ET"
                    "<br>Snapshot: %{y:.1f}%"
                    "<br>Prior 24h low: %{customdata[0]}"
                    "<br>Prior 24h high: %{customdata[1]}"
                    "<br>%{customdata[2]}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title={"text": title, "x": 0.5},
        template="plotly_white",
        hovermode="x unified",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={
            "title": "Yes probability (%)",
            "rangemode": "tozero",
            "ticksuffix": "%",
            "gridcolor": "#E5E7EB",
        },
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": 1.1},
        margin={"l": 70, "r": 35, "t": 120, "b": 90},
    )
    return figure


def create_heatmap_chart(
    dates: list[str],
    series: dict[str, list[float | None]],
    title: str,
    ranges: dict[str, dict[str, tuple[float | None, float | None]]] | None = None,
    carried_forward: dict[str, list[bool]] | None = None,
    resolution_events: list[dict[str, str]] | None = None,
) -> Any:
    """Build a readable heatmap for an event with many deadline markets."""
    import plotly.graph_objects as go

    labels = sorted(series, key=deadline_sort_key)
    values = [series[label] for label in labels]
    text: list[list[str]] = []
    customdata: list[list[list[str]]] = []
    for label, row in zip(labels, values):
        label_ranges = (ranges or {}).get(label, {})
        carried_flags = (carried_forward or {}).get(label, [False] * len(dates))
        text_row: list[str] = []
        custom_row: list[list[str]] = []
        for date_string, value, is_carried in zip(dates, row, carried_flags):
            low, high = label_ranges.get(date_string, (None, None))
            if is_carried and value is not None:
                low = high = value
            valid = low is not None and high is not None
            low_text = "n/a" if not valid else f"{low:.1f}%"
            high_text = "n/a" if not valid else f"{high:.1f}%"
            if value is None:
                text_row.append("—")
            elif is_carried:
                text_row.append(f"{value:.1f}%<br>Resolved")
            elif valid:
                text_row.append(f"{value:.1f}%<br>↕ {low:.1f}–{high:.1f}")
            else:
                text_row.append(f"{value:.1f}%")
            custom_row.append(
                [
                    low_text,
                    high_text,
                    (
                        "Resolved result carried forward"
                        if is_carried
                        else "Observed 9:00 AM snapshot"
                    ),
                ]
            )
        text.append(text_row)
        customdata.append(custom_row)
    figure = go.Figure(
        go.Heatmap(
            x=dates,
            y=labels,
            z=values,
            zmin=0,
            zmax=100,
            colorscale=[
                [0.0, "#EFF6FF"],
                [0.15, "#BFDBFE"],
                [0.4, "#60A5FA"],
                [0.7, "#2563EB"],
                [1.0, "#1E3A8A"],
            ],
            text=text,
            texttemplate="%{text}",
            customdata=customdata,
            hovertemplate=(
                "<b>%{y}</b><br>%{x} at 9:00 AM ET"
                "<br>Snapshot: %{z:.1f}%"
                "<br>Prior 24h low: %{customdata[0]}"
                "<br>Prior 24h high: %{customdata[1]}"
                "<br>%{customdata[2]}<extra></extra>"
            ),
            colorbar={"title": {"text": "Yes odds"}, "ticksuffix": "%"},
            xgap=2,
            ygap=2,
        )
    )
    marker_styles = {
        "dispute-detected": ("Dispute observed", "#DC2626", "square-open"),
        "resolved": ("Resolution observed", "#059669", "square-open"),
    }
    for event_type, (name, color, symbol) in marker_styles.items():
        matching = [
            event
            for event in (resolution_events or [])
            if event.get("Event Type") == event_type
            and event.get("Observed Date") in dates
            and event.get("Market") in labels
        ]
        if not matching:
            continue
        figure.add_trace(
            go.Scatter(
                x=[event["Observed Date"] for event in matching],
                y=[event["Market"] for event in matching],
                mode="markers",
                name=name,
                marker={
                    "symbol": symbol,
                    "size": 42,
                    "color": color,
                    "line": {"color": color, "width": 4},
                },
                customdata=[
                    [
                        event.get("Previous Status") or "unknown",
                        event.get("Current Status") or "unknown",
                        event.get("Dispute Count") or "0",
                    ]
                    for event in matching
                ],
                hovertemplate=(
                    f"<b>{name}</b><br>%{{y}}<br>Observed: %{{x}}"
                    "<br>Previous status: %{customdata[0]}"
                    "<br>Current status: %{customdata[1]}"
                    "<br>Disputes recorded: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title={"text": title, "x": 0.5},
        template="plotly_white",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={"title": "Contract date", "autorange": "reversed"},
        height=max(620, 42 * len(labels) + 170),
        legend={
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": 1.08,
        },
        margin={"l": 95, "r": 65, "t": 120, "b": 80},
    )
    return figure


def create_chart(
    dates: list[str],
    series: dict[str, list[float | None]],
    title: str,
    ranges: dict[str, dict[str, tuple[float | None, float | None]]] | None = None,
    carried_forward: dict[str, list[bool]] | None = None,
    resolution_events: list[dict[str, str]] | None = None,
) -> Any:
    """Choose a line chart or heatmap based on the number of contracts."""
    if not series:
        raise ValueError("No deadline series are available to chart")
    if len(series) <= LINE_CHART_LIMIT:
        figure = create_line_chart(
            dates,
            series,
            title,
            ranges=ranges,
            carried_forward=carried_forward,
        )
    else:
        figure = create_heatmap_chart(
            dates,
            series,
            title,
            ranges=ranges,
            carried_forward=carried_forward,
            resolution_events=resolution_events,
        )

    figure.add_annotation(
        text=(
            "Whiskers/↕ values show the observed 5-minute low–high over the prior "
            "24 hours; resolved values are derived from the final outcome after "
            "the order book stops."
        ),
        xref="paper",
        yref="paper",
        x=0,
        y=-0.2,
        showarrow=False,
        xanchor="left",
        font={"size": 11, "color": "#4B5563"},
    )
    figure.add_annotation(
        text="Source: Polymarket Gamma and CLOB APIs",
        xref="paper",
        yref="paper",
        x=1,
        y=-0.2,
        showarrow=False,
        xanchor="right",
        font={"size": 11, "color": "#6B7280"},
    )
    return figure


def write_deadline_chart(
    input_path: Path,
    output_path: Path,
    *,
    days: int,
    title: str,
    labels: set[str] | None = None,
    range_path: Path | None = None,
    resolution_status_path: Path | None = None,
    resolution_events_path: Path | None = None,
    lifecycle_path: Path | None = None,
    event_key: str | None = None,
) -> int:
    """Render a deadline chart directly from its cumulative CSV."""
    dates, series = load_snapshot(input_path, label_column=LABEL_COLUMN)
    carried_forward: dict[str, list[bool]] | None = None
    resolution_events: list[dict[str, str]] = []
    if event_key is not None:
        probabilities = (
            load_resolution_probabilities(
                resolution_status_path,
                event_key=event_key,
            )
            if resolution_status_path is not None
            else {}
        )
        closed_dates = (
            load_closed_dates(lifecycle_path, event_key=event_key)
            if lifecycle_path is not None
            else {}
        )
        dates, series, carried_forward = apply_terminal_resolutions(
            dates,
            series,
            probabilities=probabilities,
            closed_dates=closed_dates,
        )
        if resolution_events_path is not None:
            resolution_events = load_resolution_events(
                resolution_events_path,
                event_key=event_key,
            )
    all_dates = dates
    dates, series = latest_window(all_dates, series, days)
    if carried_forward is not None:
        _, carried_forward = latest_window(all_dates, carried_forward, days)
    if labels is not None:
        series = {label: values for label, values in series.items() if label in labels}
        if carried_forward is not None:
            carried_forward = {
                label: values
                for label, values in carried_forward.items()
                if label in labels
            }
    ranges = (
        load_ranges(range_path, label_column=LABEL_COLUMN)
        if range_path and range_path.exists()
        else None
    )
    figure = create_chart(
        dates,
        series,
        title,
        ranges=ranges,
        carried_forward=carried_forward,
        resolution_events=resolution_events,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(
        output_path,
        include_plotlyjs="cdn",
        full_html=True,
        config={"displaylogo": False, "responsive": True},
    )
    return len(series)


def build_parser(
    *,
    description: str,
    default_slug: str,
    default_output: Path,
    default_chart_output: Path,
) -> argparse.ArgumentParser:
    """Create the shared command-line interface for one tracked event."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--slug", default=default_slug, help="Polymarket event slug")
    parser.add_argument("--output", type=Path, default=default_output, help="CSV output path")
    parser.add_argument(
        "--range-output",
        type=Path,
        default=range_output_for_snapshot(default_output),
        help="Trailing-24-hour probability range CSV output path",
    )
    parser.add_argument(
        "--chart-output",
        type=Path,
        default=default_chart_output,
        help="HTML chart output path",
    )
    parser.add_argument("--days", type=int, default=7, help="Calendar-day snapshots")
    parser.add_argument("--hour", type=int, default=9, help="Eastern snapshot hour")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    parser.add_argument(
        "--no-chart",
        action="store_true",
        help="Update only the CSV and skip HTML chart generation",
    )
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="Include resolved deadline markets",
    )
    return parser


def run_tracker(args: argparse.Namespace) -> TrackerResult:
    """Fetch, append, and chart one deadline-based Polymarket event."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        requested_targets = snapshot_targets(
            datetime.now(tz=ZoneInfo("UTC")), days=args.days, hour=args.hour
        )
        snapshot_targets_to_add = missing_snapshot_targets(
            args.output,
            requested_targets,
            label_column=LABEL_COLUMN,
        )
        configured_range_output = getattr(args, "range_output", None)
        range_output = (
            Path(configured_range_output)
            if configured_range_output is not None
            else range_output_for_snapshot(args.output)
        )
        range_targets_to_add = missing_range_targets(
            range_output,
            requested_targets,
            label_column=LABEL_COLUMN,
        )
        targets_by_date = {
            target.date().isoformat(): target
            for target in snapshot_targets_to_add + range_targets_to_add
        }
        targets = [targets_by_date[key] for key in sorted(targets_by_date)]
    except ValueError as exc:
        logging.error("Invalid arguments: %s", exc)
        return TrackerResult("failed", exit_code=2)
    if not targets:
        logging.info("All requested snapshots and ranges already exist; no API calls were needed")
        if not args.no_chart:
            try:
                series_count = write_deadline_chart(
                    args.output,
                    args.chart_output,
                    days=args.days,
                    title=str(getattr(args, "title", "Polymarket deadline markets")),
                    range_path=range_output,
                    resolution_status_path=(
                        args.output.parent / "market_resolution_status.csv"
                    ),
                    resolution_events_path=(
                        args.output.parent / "market_resolution_events.csv"
                    ),
                    lifecycle_path=(
                        args.output.parent
                        / "market_data"
                        / "lifecycle"
                        / "market_lifecycle_events.csv"
                    ),
                    event_key=str(getattr(args, "event_key", "")) or None,
                )
            except (OSError, ValueError) as exc:
                logging.error("Could not create chart: %s", exc)
                return TrackerResult("failed", exit_code=1)
            logging.info(
                "Created chart with %d stored markets at %s",
                series_count,
                args.chart_output,
            )
        return TrackerResult("current")

    session = build_session()
    try:
        event = fetch_event(session, args.slug, args.timeout)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        logging.error("Could not fetch event: %s", exc)
        return TrackerResult("failed", exit_code=1)

    event_markets = event.get("markets", [])
    if not isinstance(event_markets, list) or not event_markets:
        logging.error("The event contains no markets")
        return TrackerResult("failed", exit_code=1)
    event_closed = all_markets_closed(event_markets)
    if event_closed:
        stored_dates = stored_snapshot_dates(args.output, label_column=LABEL_COLUMN)
        snapshot_targets_to_add = []
        stored_targets = [
            datetime.combine(
                date.fromisoformat(date_string),
                time(args.hour),
                tzinfo=ZoneInfo("America/New_York"),
            )
            for date_string in sorted(stored_dates)[-args.days :]
        ]
        range_targets_to_add = missing_range_targets(
            range_output,
            stored_targets,
            label_column=LABEL_COLUMN,
        )
        logging.info("All event markets are closed; no snapshot date will be appended")

    snapshot_markets = selected_markets(
        event_markets,
        include_closed=args.include_closed and not event_closed,
    )
    if not event_closed and not snapshot_markets:
        logging.error("The event contains no markets matching the requested status")
        return TrackerResult("failed", exit_code=1)

    targets_by_date = {
        target.date().isoformat(): target
        for target in snapshot_targets_to_add + range_targets_to_add
    }
    targets = [targets_by_date[key] for key in sorted(targets_by_date)]
    rows: list[dict[str, Any]] = []
    range_rows: list[dict[str, Any]] = []
    if targets:
        history_markets = event_markets if range_targets_to_add else snapshot_markets
        logging.info(
            "Fetching %d deadline markets for snapshots and ranges",
            len(history_markets),
        )
        rows, range_rows = collect_rows_and_ranges(
            session,
            history_markets,
            targets,
            args.timeout,
            label_column=LABEL_COLUMN,
        )
        snapshot_labels = {
            str(market.get("groupItemTitle") or market.get("question") or "Unknown market")
            for market in snapshot_markets
        }
        rows = [row for row in rows if str(row.get(LABEL_COLUMN)) in snapshot_labels]
    try:
        added_dates, total_rows = merge_and_write_csv(
            args.output,
            rows,
            snapshot_targets_to_add,
            label_column=LABEL_COLUMN,
        )
        added_ranges, total_ranges = merge_and_write_range_csv(
            range_output,
            range_rows,
            label_column=LABEL_COLUMN,
        )
        series_count = 0
        if not args.no_chart:
            series_count = write_deadline_chart(
                args.output,
                args.chart_output,
                days=args.days,
                title=str(
                    event.get("title")
                    or getattr(args, "title", "Polymarket deadline markets")
                ),
                range_path=range_output,
                resolution_status_path=(
                    args.output.parent / "market_resolution_status.csv"
                ),
                resolution_events_path=(
                    args.output.parent / "market_resolution_events.csv"
                ),
                lifecycle_path=(
                    args.output.parent
                    / "market_data"
                    / "lifecycle"
                    / "market_lifecycle_events.csv"
                ),
                event_key=str(getattr(args, "event_key", "")) or None,
            )
    except (OSError, ValueError) as exc:
        logging.error("Could not create output: %s", exc)
        return TrackerResult("failed", exit_code=1)

    logging.info(
        "Added %d new date(s); CSV contains %d stored rows at %s; "
        "stored %d new range row(s) (%d total) at %s",
        added_dates,
        total_rows,
        args.output,
        added_ranges,
        total_ranges,
        range_output,
    )
    if not args.no_chart:
        logging.info("Created chart with %d stored markets at %s", series_count, args.chart_output)
    status = "closed" if event_closed else ("appended" if added_dates else "current")
    return TrackerResult(status, added_dates=added_dates, row_count=total_rows)
