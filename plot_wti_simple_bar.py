#!/usr/bin/env python3
"""Create a simple seven-day bar chart highlighting daily odds increases."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from plot_wti_timeseries import DEFAULT_INPUT, latest_window, load_snapshot


DEFAULT_OUTPUT = Path("wti_simple_7_day_bar.html")
DEFAULT_PRICE_BIN = "↑ $90"


def bar_segments(
    values: list[float | None],
) -> tuple[list[float | None], list[float | None]]:
    """Split each bar into its prior-day base and any positive daily increase."""
    bases: list[float | None] = []
    increases: list[float | None] = []
    previous: float | None = None
    for value in values:
        if value is None:
            bases.append(None)
            increases.append(None)
            previous = None
            continue
        if previous is not None and value > previous:
            bases.append(previous)
            increases.append(value - previous)
        else:
            bases.append(value)
            increases.append(0.0)
        previous = value
    return bases, increases


def create_chart(
    dates: list[str], values: list[float | None], price_bin: str
) -> Any:
    """Build a stacked bar chart whose dark segment is the daily odds increase."""
    import plotly.graph_objects as go

    bases, increases = bar_segments(values)
    is_up_market = price_bin.startswith("↑")
    light_color = "#93C5FD" if is_up_market else "#FDBA74"
    deep_color = "#1D4ED8" if is_up_market else "#C2410C"
    comparisons = []
    previous: float | None = None
    for value in values:
        if value is None:
            comparisons.append([None, None, None])
            previous = None
            continue
        change = None if previous is None else value - previous
        comparisons.append([value, previous, change])
        previous = value

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=dates,
            y=bases,
            name="Odds excluding daily increase",
            marker={"color": light_color},
            customdata=comparisons,
            hovertemplate=(
                "<b>%{x}</b><br>Odds: %{customdata[0]:.1f}%"
                "<br>Prior day: %{customdata[1]:.1f}%"
                "<br>Change: %{customdata[2]:+.1f} pp<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Bar(
            x=dates,
            y=increases,
            name="Increase from prior day",
            marker={"color": deep_color},
            customdata=comparisons,
            hovertemplate=(
                "<b>%{x}</b><br>Odds: %{customdata[0]:.1f}%"
                "<br>Increase: %{customdata[2]:+.1f} pp<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            mode="text",
            text=[None if value is None else f"{value:.1f}%" for value in values],
            textposition="top center",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    available_values = [value for value in values if value is not None]
    if not available_values:
        raise ValueError(f"No values are available for {price_bin}")
    y_maximum = max(1.0, max(available_values) * 1.2)
    figure.update_layout(
        title={"text": f"WTI July 2026 odds — {price_bin}", "x": 0.5},
        barmode="stack",
        bargap=0.28,
        template="plotly_white",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={
            "title": "Implied probability (%)",
            "range": [0, y_maximum],
            "ticksuffix": "%",
            "gridcolor": "#E5E7EB",
        },
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": 1.08},
        hovermode="x unified",
        margin={"l": 70, "r": 35, "t": 120, "b": 85},
        annotations=[
            {
                "text": "Darker sections show only the increase from the previous day.",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.22,
                "showarrow": False,
                "xanchor": "left",
                "font": {"size": 11, "color": "#4B5563"},
            },
            {
                "text": "Source: Polymarket Gamma and CLOB APIs",
                "xref": "paper",
                "yref": "paper",
                "x": 1,
                "y": -0.22,
                "showarrow": False,
                "xanchor": "right",
                "font": {"size": 11, "color": "#6B7280"},
            },
        ],
    )
    return figure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a simple seven-day WTI odds bar chart."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Snapshot CSV path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML path")
    parser.add_argument(
        "--price-bin", default=DEFAULT_PRICE_BIN, help="Exact Price Bin label to chart"
    )
    parser.add_argument("--days", type=int, default=7, help="Most recent days to chart")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dates, series = load_snapshot(args.input)
        dates, series = latest_window(dates, series, args.days)
        if args.price_bin not in series:
            available = ", ".join(series)
            raise ValueError(
                f"Price bin {args.price_bin!r} is not present. Choose from: {available}"
            )
        figure = create_chart(dates, series[args.price_bin], args.price_bin)
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
