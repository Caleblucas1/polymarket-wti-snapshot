#!/usr/bin/env python3
"""Create an interactive seven-day chart from a WTI snapshot CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("wti_july_2026_9am_snapshot.csv")
DEFAULT_OUTPUT = Path("wti_7_day_time_series.html")


def load_snapshot(path: Path) -> tuple[list[str], dict[str, list[float | None]]]:
    """Load and validate price-bin time series from a snapshot CSV."""
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames or "Price Bin" not in reader.fieldnames:
            raise ValueError("CSV must contain a 'Price Bin' column")

        dates = [column for column in reader.fieldnames if column != "Price Bin"]
        if not dates:
            raise ValueError("CSV must contain at least one date column")
        for date_string in dates:
            try:
                date.fromisoformat(date_string)
            except ValueError as exc:
                raise ValueError(f"Invalid ISO date column: {date_string}") from exc

        series: dict[str, list[float | None]] = {}
        for row_number, row in enumerate(reader, start=2):
            label = (row.get("Price Bin") or "").strip()
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


def create_chart(
    dates: list[str], series: dict[str, list[float | None]]
) -> Any:
    """Build a Plotly chart with price-bin and y-axis scale controls."""
    import plotly.graph_objects as go

    labels = list(series)
    default_label = "↑ $90" if "↑ $90" in series else labels[0]
    default_index = labels.index(default_label)
    figure = go.Figure()

    for index, (label, values) in enumerate(series.items()):
        color = "#2878B5" if label.startswith("↑") else "#D97706"
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
                hovertemplate=(
                    f"<b>{label}</b><br>%{{x}} at 9:00 AM ET"
                    "<br>%{y:.1f}% implied probability<extra></extra>"
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
                    {"title.text": f"WTI July 2026 probability — {label}"},
                ],
            }
        )

    figure.update_layout(
        title={"text": f"WTI July 2026 probability — {default_label}", "x": 0.5},
        xaxis={
            "title": "Daily snapshot at 9:00 AM ET",
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
                "text": "Source: Polymarket Gamma and CLOB APIs",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an interactive seven-day chart from a WTI snapshot CSV."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Snapshot CSV path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML path")
    parser.add_argument("--days", type=int, default=7, help="Most recent days to chart")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dates, series = load_snapshot(args.input)
        dates, series = latest_window(dates, series, args.days)
        figure = create_chart(dates, series)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(
            args.output,
            include_plotlyjs="cdn",
            full_html=True,
            config={"displaylogo": False, "responsive": True},
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
