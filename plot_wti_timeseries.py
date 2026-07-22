#!/usr/bin/env python3
"""Create an interactive seven-day chart from a WTI snapshot CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any


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
) -> Any:
    """Build a Plotly chart with trailing-24-hour range whiskers."""
    import plotly.graph_objects as go

    labels = list(series)
    default_label = "↑ $90" if "↑ $90" in series else labels[0]
    default_index = labels.index(default_label)
    figure = go.Figure()

    for index, (label, values) in enumerate(series.items()):
        color = "#2878B5" if label.startswith("↑") else "#D97706"
        label_ranges = (ranges or {}).get(label, {})
        lows: list[float | None] = []
        highs: list[float | None] = []
        upper_errors: list[float | None] = []
        lower_errors: list[float | None] = []
        for date_string, value in zip(dates, values):
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
                x=dates,
                y=values,
                mode="lines+markers+text",
                name=label,
                visible=index == default_index,
                line={"color": color, "width": 3},
                marker={"color": color, "size": 9},
                text=[None if value is None else f"{value:.1f}%" for value in values],
                textposition="top center",
                customdata=[
                    [
                        "n/a" if low is None else f"{low:.1f}%",
                        "n/a" if high is None else f"{high:.1f}%",
                    ]
                    for low, high in zip(lows, highs)
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
                    f"<b>{label}</b><br>%{{x}} at 9:00 AM ET"
                    "<br>Snapshot: %{y:.1f}%"
                    "<br>Prior 24h low: %{customdata[0]}"
                    "<br>Prior 24h high: %{customdata[1]}<extra></extra>"
                ),
            )
        )

    price_bin_buttons = []
    for index, label in enumerate(labels):
        visibility = [trace_index == index for trace_index in range(len(labels))]
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

    figure.update_layout(
        title={"text": f"{title_prefix} — {default_label}", "x": 0.5},
        xaxis={
            "title": "9:00 AM ET snapshot; whiskers show the preceding 24-hour range",
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
        margin={"l": 70, "r": 35, "t": 125, "b": 80},
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
                        "label": "0–100% scale",
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
        annotations=[
            {
                "text": "Price bin",
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
                "text": "Whiskers: observed 5-minute low–high over the prior 24 hours. Source: Polymarket Gamma and CLOB APIs",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.2,
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
) -> int:
    """Render a saved snapshot CSV and return the number of plotted series."""
    dates, series = load_snapshot(input_path, label_column=label_column)
    dates, series = latest_window(dates, series, days)
    if labels is not None:
        series = {label: values for label, values in series.items() if label in labels}
    if not series:
        raise ValueError("No stored series match the requested chart filters")
    ranges = load_ranges(range_path, label_column=label_column) if range_path and range_path.exists() else None
    figure = create_chart(dates, series, title_prefix=title_prefix, ranges=ranges)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(
        output_path,
        include_plotlyjs="cdn",
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML path")
    parser.add_argument("--days", type=int, default=7, help="Most recent days to chart")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        write_chart(args.input, args.output, range_path=args.range_input, days=args.days)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
