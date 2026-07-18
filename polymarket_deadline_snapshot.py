#!/usr/bin/env python3
"""Reusable snapshot and chart workflow for Polymarket deadline events."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

from plot_wti_timeseries import latest_window, load_snapshot
from polymarket_wti_snapshot import (
    all_markets_closed,
    build_session,
    collect_rows,
    fetch_event,
    merge_and_write_csv,
    market_is_closed,
    missing_snapshot_targets,
    snapshot_targets,
    TrackerResult,
)


LABEL_COLUMN = "Deadline"
LINE_CHART_LIMIT = 8


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
                hovertemplate=(
                    f"<b>{label}</b><br>%{{x}} at 9:00 AM ET"
                    "<br>%{y:.1f}% Yes probability<extra></extra>"
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
) -> Any:
    """Build a readable heatmap for an event with many deadline markets."""
    import plotly.graph_objects as go

    labels = sorted(series, key=deadline_sort_key)
    values = [series[label] for label in labels]
    text = [
        ["—" if value is None else f"{value:.1f}%" for value in row]
        for row in values
    ]
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
            hovertemplate=(
                "<b>%{y}</b><br>%{x} at 9:00 AM ET"
                "<br>%{z:.1f}% Yes probability<extra></extra>"
            ),
            colorbar={"title": {"text": "Yes odds"}, "ticksuffix": "%"},
            xgap=2,
            ygap=2,
        )
    )
    figure.update_layout(
        title={"text": title, "x": 0.5},
        template="plotly_white",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={"title": "Contract date", "autorange": "reversed"},
        height=max(620, 34 * len(labels) + 170),
        margin={"l": 95, "r": 65, "t": 90, "b": 80},
    )
    return figure


def create_chart(
    dates: list[str],
    series: dict[str, list[float | None]],
    title: str,
) -> Any:
    """Choose a line chart or heatmap based on the number of contracts."""
    if not series:
        raise ValueError("No deadline series are available to chart")
    if len(series) <= LINE_CHART_LIMIT:
        figure = create_line_chart(dates, series, title)
    else:
        figure = create_heatmap_chart(dates, series, title)

    figure.add_annotation(
        text="Stored deadline series are shown; fully closed events remain frozen.",
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
) -> int:
    """Render a deadline chart directly from its cumulative CSV."""
    dates, series = load_snapshot(input_path, label_column=LABEL_COLUMN)
    dates, series = latest_window(dates, series, days)
    if labels is not None:
        series = {label: values for label, values in series.items() if label in labels}
    figure = create_chart(dates, series, title)
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
        targets = snapshot_targets(
            datetime.now(tz=ZoneInfo("UTC")), days=args.days, hour=args.hour
        )
        targets = missing_snapshot_targets(
            args.output,
            targets,
            label_column=LABEL_COLUMN,
        )
    except ValueError as exc:
        logging.error("Invalid arguments: %s", exc)
        return TrackerResult("failed", exit_code=2)
    if not targets:
        if args.no_chart:
            logging.info("All requested snapshot dates already exist; no API calls were needed")
            return TrackerResult("current")
        logging.info("All requested snapshot dates already exist; skipped history API calls")
        session = build_session()
        try:
            event = fetch_event(session, args.slug, args.timeout)
            event_markets = event.get("markets", [])
            if not isinstance(event_markets, list) or not event_markets:
                raise ValueError("The event contains no markets")
            event_closed = all_markets_closed(event_markets)
            chart_markets = (
                event_markets
                if event_closed
                else selected_markets(event_markets, include_closed=args.include_closed)
            )
            labels = {
                str(market.get("groupItemTitle") or market.get("question") or "Unknown market")
                for market in chart_markets
            }
            series_count = write_deadline_chart(
                args.output,
                args.chart_output,
                days=args.days,
                title=str(
                    event.get("title")
                    or getattr(args, "title", "Polymarket deadline markets")
                ),
                labels=labels,
            )
        except (requests.RequestException, OSError, ValueError, json.JSONDecodeError) as exc:
            logging.error("Could not create chart: %s", exc)
            return TrackerResult("failed", exit_code=1)
        logging.info("Created chart with %d stored markets at %s", series_count, args.chart_output)
        return TrackerResult("closed" if event_closed else "current")

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
    if all_markets_closed(event_markets):
        logging.info("All event markets are closed; no snapshot date was appended")
        if not args.no_chart and args.output.exists():
            try:
                series_count = write_deadline_chart(
                    args.output,
                    args.chart_output,
                    days=args.days,
                    title=str(
                        event.get("title")
                        or getattr(args, "title", "Polymarket deadline markets")
                    ),
                    labels={
                        str(
                            market.get("groupItemTitle")
                            or market.get("question")
                            or "Unknown market"
                        )
                        for market in event_markets
                    },
                )
            except (OSError, ValueError) as exc:
                logging.error("Could not create chart: %s", exc)
                return TrackerResult("failed", exit_code=1)
            logging.info(
                "Created chart with %d stored markets at %s",
                series_count,
                args.chart_output,
            )
        return TrackerResult("closed")
    markets = selected_markets(event_markets, include_closed=args.include_closed)
    if not markets:
        logging.error("The event contains no markets matching the requested status")
        return TrackerResult("failed", exit_code=1)

    logging.info("Fetching %d unresolved deadline markets", len(markets))
    rows = collect_rows(
        session,
        markets,
        targets,
        args.timeout,
        label_column=LABEL_COLUMN,
    )
    try:
        added_dates, total_rows = merge_and_write_csv(
            args.output,
            rows,
            targets,
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
                labels={
                    str(market.get("groupItemTitle") or market.get("question") or "Unknown market")
                    for market in markets
                },
            )
    except (OSError, ValueError) as exc:
        logging.error("Could not create output: %s", exc)
        return TrackerResult("failed", exit_code=1)

    logging.info(
        "Added %d new date(s); CSV contains %d stored rows at %s",
        added_dates,
        total_rows,
        args.output,
    )
    if not args.no_chart:
        logging.info("Created chart with %d stored markets at %s", series_count, args.chart_output)
    status = "appended" if added_dates else "current"
    return TrackerResult(status, added_dates=added_dates, row_count=total_rows)
