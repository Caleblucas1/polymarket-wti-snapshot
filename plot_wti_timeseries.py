#!/usr/bin/env python3
"""Create an interactive seven-day chart from a WTI snapshot CSV."""

from __future__ import annotations

import argparse
import csv
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from chart_output import plotly_basic_cdn


DEFAULT_INPUT = Path("wti_july_2026_9am_snapshot.csv")
DEFAULT_RANGE_INPUT = Path("wti_july_2026_9am_ranges.csv")
DEFAULT_OUTPUT = Path("wti_7_day_time_series.html")


def load_snapshot(
    path: Path, label_column: str = "Price Bin"
) -> tuple[list[str], dict[str, list[float | None]]]:
    """Load and validate price-bin time series from a snapshot CSV."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames or label_column not in reader.fieldnames:
            raise ValueError(f"CSV must contain a {label_column!r} column")

        dates = [column for column in reader.fieldnames if column != label_column]
        if not dates:
            raise ValueError("CSV must contain at least one date column")
        for date_string in dates:
            try:
                date.fromisoformat(date_string)
            except ValueError as exc:
                raise ValueError(f"Invalid ISO date column: {date_string}") from exc

        series: dict[str, list[float | None]] = {}
        for row_number, row in enumerate(reader, start=2):
            label = (row.get(label_column) or "").strip()
            if not label:
                raise ValueError(f"Missing price-bin label on row {row_number}")
            values: list[float | None] = []
            for date_string in dates:
                raw_value = (row.get(date_string) or "").strip()
                if not raw_value:
                    values.append(None)
                    continue
                try:
                    value = float(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid percentage for {label} on {date_string}: {raw_value}"
                    ) from exc
                if not 0 <= value <= 100:
                    raise ValueError(
                        f"Percentage outside 0-100 for {label} on {date_string}: {value}"
                    )
                values.append(value)
            series[label] = values

    if not series:
        raise ValueError("CSV contains no price-bin rows")
    return dates, series


def latest_window(
    dates: list[str],
    series: dict[str, list[float | None]],
    days: int = 7,
) -> tuple[list[str], dict[str, list[float | None]]]:
    """Select the most recent calendar-date columns for charting."""
    if days < 1:
        raise ValueError("days must be at least 1")
    selected_indices = sorted(range(len(dates)), key=lambda index: dates[index])[-days:]
    selected_dates = [dates[index] for index in selected_indices]
    selected_series = {
        label: [values[index] for index in selected_indices]
        for label, values in series.items()
    }
    return selected_dates, selected_series


def parse_api_datetime(value: str) -> datetime | None:
    """Parse Gamma timestamps, including its legacy UTC offset variants."""
    normalized = value.strip().replace("Z", "+00:00")
    if not normalized:
        return None
    if normalized.endswith("+00"):
        normalized = f"{normalized}:00"
    if normalized.endswith("+00:00:00"):
        normalized = normalized[:-3]
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed


def load_condition_status(
    path: Path,
    *,
    event_key: str,
) -> list[dict[str, Any]]:
    """Load physical-condition timing, live price, and resolution state."""
    if not path.exists():
        return []
    required = {
        "Event Key",
        "Market",
        "Condition ID",
        "Closed",
        "Last Checked",
        "Condition Created At",
        "Resolved At",
        "Current Yes Probability",
        "Resolved Outcome",
    }
    conditions: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            return []
        for row in reader:
            if str(row.get("Event Key") or "").strip() != event_key:
                continue
            raw_probability = str(row.get("Current Yes Probability") or "").strip()
            try:
                current_probability = (
                    None if not raw_probability else float(raw_probability)
                )
            except ValueError:
                current_probability = None
            conditions.append(
                {
                    "label": str(row.get("Market") or "").strip(),
                    "condition_id": str(row.get("Condition ID") or "").strip(),
                    "created_at": parse_api_datetime(
                        str(row.get("Condition Created At") or "")
                    ),
                    "resolved_at": parse_api_datetime(
                        str(row.get("Resolved At") or "")
                    ),
                    "last_checked": parse_api_datetime(
                        str(row.get("Last Checked") or "")
                    ),
                    "closed": str(row.get("Closed") or "").strip().lower()
                    == "true",
                    "resolved_yes": (
                        str(row.get("Resolved Outcome") or "").strip().lower()
                        == "yes"
                    ),
                    "resolved_outcome": str(row.get("Resolved Outcome") or "").strip(),
                    "automatically_resolved": str(
                        row.get("Automatically Resolved") or ""
                    ).strip(),
                    "current_probability": current_probability,
                }
            )
    return conditions


def mask_inactive_condition_dates(
    dates: list[str],
    series: dict[str, list[float | None]],
    conditions: list[dict[str, Any]],
) -> dict[str, list[float | None]]:
    """Hide values at 9 AM when no physical condition was actually active."""
    eastern = ZoneInfo("America/New_York")
    by_label: dict[str, list[dict[str, Any]]] = {}
    for condition in conditions:
        by_label.setdefault(str(condition["label"]), []).append(condition)
    masked: dict[str, list[float | None]] = {}
    for label, source_values in series.items():
        label_conditions = [
            condition
            for condition in by_label.get(label, [])
            if condition.get("created_at") is not None
        ]
        if not label_conditions:
            masked[label] = list(source_values)
            continue
        values = list(source_values)
        for index, date_string in enumerate(dates):
            target = datetime.combine(
                date.fromisoformat(date_string),
                time(9),
                tzinfo=eastern,
            )
            active = any(
                condition["created_at"] <= target
                and (
                    condition.get("resolved_at") is None
                    or target < condition["resolved_at"]
                )
                for condition in label_conditions
            )
            if not active:
                values[index] = None
        masked[label] = values
    return masked


def satisfaction_events(
    conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every physical condition observed resolving Yes."""
    events = [
        condition
        for condition in conditions
        if condition.get("resolved_yes")
        and condition.get("resolved_at") is not None
    ]
    return sorted(events, key=lambda condition: condition["resolved_at"])


def resolution_method(value: str) -> str:
    """Return a reader-facing resolution method."""
    normalized = str(value or "").strip().lower()
    if normalized == "true":
        return "Automatic"
    if normalized == "false":
        return "Manual/UMA"
    return "Unknown"


def format_resolution_timestamp(value: datetime | None) -> str:
    """Format a resolution timestamp for chart hover text."""
    if value is None:
        return "Unknown"
    eastern = value.astimezone(ZoneInfo("America/New_York"))
    return eastern.strftime("%B %d, %Y %I:%M %p ET").replace(" 0", " ")


def latest_active_points(
    conditions: list[dict[str, Any]],
) -> dict[str, tuple[str, float]]:
    """Return the newest active physical condition's live price per label."""
    active_by_label: dict[str, dict[str, Any]] = {}
    for condition in conditions:
        if (
            condition.get("closed")
            or condition.get("resolved_at") is not None
            or condition.get("current_probability") is None
            or condition.get("last_checked") is None
        ):
            continue
        label = str(condition["label"])
        existing = active_by_label.get(label)
        created_at = condition.get("created_at") or datetime.min.replace(
            tzinfo=ZoneInfo("UTC")
        )
        existing_created = (
            existing.get("created_at")
            if existing is not None
            else datetime.min.replace(tzinfo=ZoneInfo("UTC"))
        )
        if existing is None or created_at > existing_created:
            active_by_label[label] = condition
    return {
        label: (
            condition["last_checked"].isoformat(timespec="seconds"),
            float(condition["current_probability"]),
        )
        for label, condition in active_by_label.items()
    }


def price_threshold(label: str) -> float:
    """Return the numeric threshold used to split lower and upper panels."""
    match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", label)
    return float(match.group(1)) if match else float("inf")


def load_ranges(
    path: Path,
    *,
    label_column: str = "Price Bin",
) -> dict[str, dict[str, tuple[float | None, float | None]]]:
    """Load cumulative low/high ranges keyed by price bin and date."""
    ranges: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        required = {label_column, "Date", "Low", "High"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Range CSV must contain {', '.join(sorted(required))}")
        seen: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            label = str(row.get(label_column) or "").strip()
            date_string = str(row.get("Date") or "").strip()
            if not label:
                raise ValueError(f"Missing price-bin label on range row {row_number}")
            try:
                date.fromisoformat(date_string)
            except ValueError as exc:
                raise ValueError(f"Invalid range date: {date_string}") from exc
            key = (label, date_string)
            if key in seen:
                raise ValueError(f"Duplicate range row for {label} on {date_string}")
            seen.add(key)
            values: list[float | None] = []
            for field in ("Low", "High"):
                raw_value = str(row.get(field) or "").strip()
                if not raw_value:
                    values.append(None)
                    continue
                try:
                    value = float(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid {field.lower()} for {label} on {date_string}: {raw_value}"
                    ) from exc
                if not 0 <= value <= 100:
                    raise ValueError(
                        f"Range percentage outside 0-100 for {label} on {date_string}: {value}"
                    )
                values.append(value)
            low, high = values
            if low is not None and high is not None and low > high:
                raise ValueError(f"Range low exceeds high for {label} on {date_string}")
            ranges.setdefault(label, {})[date_string] = (low, high)
    return ranges


def create_chart(
    dates: list[str],
    series: dict[str, list[float | None]],
    title_prefix: str = "WTI July 2026 probability",
    ranges: dict[str, dict[str, tuple[float | None, float | None]]] | None = None,
    resolved_events: list[dict[str, Any]] | None = None,
    live_points: dict[str, tuple[str, float]] | None = None,
) -> Any:
    """Build a single-condition chart with ranges and condition lifecycle markers."""
    import plotly.graph_objects as go

    labels = sorted(series, key=lambda label: (price_threshold(label), label))
    default_label = (
        "↑ $90"
        if "↑ $90" in series
        else next((label for label in labels if any(value is not None for value in series[label])), labels[0])
    )
    default_index = labels.index(default_label)
    figure = go.Figure()
    palette = [
        "#2563EB",
        "#DC2626",
        "#059669",
        "#7C3AED",
        "#D97706",
        "#0891B2",
        "#DB2777",
        "#4F46E5",
        "#65A30D",
        "#EA580C",
        "#0F766E",
        "#9333EA",
    ]

    for index, label in enumerate(labels):
        values = series[label]
        color = palette[index % len(palette)]
        label_ranges = (ranges or {}).get(label, {})
        trace_dates = list(dates)
        trace_values = list(values)
        statuses = ["Observed 9:00 AM snapshot"] * len(trace_dates)
        live = (live_points or {}).get(label)
        if live is not None:
            live_date, live_value = live
            if not trace_dates or live_date > trace_dates[-1]:
                trace_dates.append(live_date)
                trace_values.append(live_value)
                statuses.append("Latest active replacement condition")
        lows: list[float | None] = []
        highs: list[float | None] = []
        upper_errors: list[float | None] = []
        lower_errors: list[float | None] = []
        for date_string, value, status in zip(trace_dates, trace_values, statuses):
            low, high = label_ranges.get(date_string, (None, None))
            if (
                value is None
                or low is None
                or high is None
                or not low <= value <= high
            ):
                lows.append(None)
                highs.append(None)
                lower_errors.append(None)
                upper_errors.append(None)
            else:
                lows.append(low)
                highs.append(high)
                lower_errors.append(value - low)
                upper_errors.append(high - value)
        figure.add_trace(
            go.Scatter(
                x=trace_dates,
                y=trace_values,
                mode="lines+markers",
                name=label,
                legendgroup=label,
                visible=index == default_index,
                line={
                    "color": color,
                    "width": 2,
                    "dash": "solid" if label.startswith("↑") else "dash",
                },
                marker={
                    "color": color,
                    "size": [
                        10 if status.startswith("Latest") else 6
                        for status in statuses
                    ],
                    "symbol": [
                        "diamond" if status.startswith("Latest") else "circle"
                        for status in statuses
                    ],
                },
                customdata=[
                    [
                        "n/a" if low is None else f"{low:.1f}%",
                        "n/a" if high is None else f"{high:.1f}%",
                        status,
                    ]
                    for low, high, status in zip(lows, highs, statuses)
                ],
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": upper_errors,
                    "arrayminus": lower_errors,
                    "color": color,
                    "thickness": 2,
                    "width": 8,
                    "visible": any(value is not None for value in upper_errors),
                },
                hovertemplate=(
                    f"<b>{label}</b><br>%{{x}}"
                    "<br>Probability: %{y:.1f}%"
                    "<br>Prior 24h low: %{customdata[0]}"
                    "<br>Prior 24h high: %{customdata[1]}"
                    "<br>%{customdata[2]}<extra></extra>"
                ),
            )
        )

    visible_start = date.fromisoformat(min(dates))
    visible_end = date.fromisoformat(max(dates))
    resolution_marker_count = sum(
        1
        for event in (resolved_events or [])
        if event.get("resolved_at") is not None
        and visible_start <= event["resolved_at"].date() <= visible_end
    )
    price_bin_buttons = []
    for index, label in enumerate(labels):
        visibility = [trace_index == index for trace_index in range(len(labels))]
        visibility.extend([True] * resolution_marker_count)
        price_bin_buttons.append(
            {
                "label": label,
                "method": "update",
                "args": [
                    {"visible": visibility},
                    {"title.text": f"{title_prefix} — {label}"},
                ],
            }
        )

    annotations: list[dict[str, Any]] = []
    shapes: list[dict[str, Any]] = []
    for event_index, event in enumerate(resolved_events or []):
        resolved_at = event.get("resolved_at")
        if (
            resolved_at is None
            or resolved_at.date() < visible_start
            or resolved_at.date() > visible_end
        ):
            continue
        timestamp = resolved_at.isoformat(timespec="seconds")
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": timestamp,
                "x1": timestamp,
                "y0": 0,
                "y1": 1,
                "line": {"color": "#DC2626", "width": 1.5, "dash": "dot"},
            }
        )
        annotations.append(
            {
                "text": f"{event['label']} Yes",
                "xref": "x",
                "yref": "paper",
                "x": timestamp,
                "y": 1.04 + 0.045 * (event_index % 3),
                "showarrow": False,
                "textangle": -35,
                "font": {"size": 10, "color": "#B91C1C"},
                "bgcolor": "rgba(255,255,255,0.82)",
            }
        )
        figure.add_trace(
            go.Scatter(
                x=[timestamp],
                y=[0],
                mode="markers",
                name=f"{event['label']} resolution",
                showlegend=False,
                marker={"size": 14, "color": "rgba(220,38,38,0.02)"},
                customdata=[
                    [
                        event.get("resolved_outcome") or "Yes",
                        format_resolution_timestamp(resolved_at),
                        resolution_method(event.get("automatically_resolved", "")),
                    ]
                ],
                hovertemplate=(
                    f"<b>{event['label']}</b><br>Resolution observed: %{{x}}"
                    "<br>Resolved: %{customdata[0]}"
                    "<br>Resolution date: %{customdata[1]}"
                    "<br>Resolution method: %{customdata[2]}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title={"text": f"{title_prefix} — {default_label}", "x": 0.5},
        xaxis={
            "title": "Daily snapshot at 9:00 AM ET plus latest active-condition reading",
            "type": "date",
            "showgrid": False,
        },
        yaxis={
            "title": "Implied probability (%)",
            "rangemode": "tozero",
            "ticksuffix": "%",
            "gridcolor": "#E5E7EB",
        },
        template="plotly_white",
        showlegend=False,
        hovermode="x unified",
        height=640,
        margin={"l": 70, "r": 35, "t": 135, "b": 95},
        updatemenus=[
            {
                "buttons": price_bin_buttons,
                "direction": "down",
                "showactive": True,
                "x": 0,
                "xanchor": "left",
                "y": 1.18,
                "yanchor": "top",
            },
            {
                "buttons": [
                    {
                        "label": "Auto scale",
                        "method": "relayout",
                        "args": [{"yaxis.autorange": True}],
                    },
                    {
                        "label": "0-100% scale",
                        "method": "relayout",
                        "args": [{"yaxis.range": [0, 100]}],
                    },
                ],
                "direction": "down",
                "showactive": True,
                "x": 0.28,
                "xanchor": "left",
                "y": 1.18,
                "yanchor": "top",
            },
        ],
        shapes=shapes,
        annotations=[
            *annotations,
            {
                "text": "Price condition",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": 1.25,
                "showarrow": False,
                "xanchor": "left",
            },
            {
                "text": "Scale",
                "xref": "paper",
                "yref": "paper",
                "x": 0.28,
                "y": 1.25,
                "showarrow": False,
                "xanchor": "left",
            },
            {
                "text": (
                    "Red lines: physical conditions resolved Yes. "
                    "Lines restart with the newest active replacement; terminal "
                    "100% values are not carried forward. Diamonds are live values. "
                    "Whiskers show the prior 24-hour observed range."
                ),
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.22,
                "showarrow": False,
                "xanchor": "left",
                "font": {"size": 11, "color": "#6B7280"},
            },
        ],
    )
    return figure


def write_chart(
    input_path: Path,
    output_path: Path,
    *,
    days: int = 7,
    label_column: str = "Price Bin",
    title_prefix: str = "WTI July 2026 probability",
    labels: set[str] | None = None,
    range_path: Path | None = None,
    resolution_status_path: Path | None = None,
    event_key: str = "wti-july",
) -> int:
    """Render a saved snapshot CSV and return the number of plotted series."""
    dates, series = load_snapshot(input_path, label_column=label_column)
    conditions = (
        load_condition_status(resolution_status_path, event_key=event_key)
        if resolution_status_path is not None
        else []
    )
    if conditions:
        series = mask_inactive_condition_dates(dates, series, conditions)
    dates, series = latest_window(dates, series, days)
    if labels is not None:
        series = {label: values for label, values in series.items() if label in labels}
    if not series:
        raise ValueError("No stored series match the requested chart filters")
    ranges = load_ranges(range_path, label_column=label_column) if range_path and range_path.exists() else None
    figure = create_chart(
        dates,
        series,
        title_prefix=title_prefix,
        ranges=ranges,
        resolved_events=satisfaction_events(conditions),
        live_points=latest_active_points(conditions),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(
        output_path,
        include_plotlyjs=plotly_basic_cdn(),
        full_html=True,
        config={"displaylogo": False, "responsive": True},
    )
    return len(series)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an interactive seven-day chart from a WTI snapshot CSV."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Snapshot CSV path")
    parser.add_argument(
        "--range-input",
        type=Path,
        default=DEFAULT_RANGE_INPUT,
        help="Trailing-24-hour range CSV path",
    )
    parser.add_argument(
        "--resolution-status",
        type=Path,
        default=Path("market_resolution_status.csv"),
        help="Physical-condition status inventory",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML path")
    parser.add_argument("--days", type=int, default=7, help="Most recent days to chart")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        write_chart(
            args.input,
            args.output,
            range_path=args.range_input,
            resolution_status_path=args.resolution_status,
            days=args.days,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
