#!/usr/bin/env python3
"""Snapshot and chart the Bab el-Mandeb effective-closure markets."""

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
    build_session,
    collect_rows,
    fetch_event,
    merge_and_write_csv,
    snapshot_targets,
)


DEFAULT_SLUG = "bab-el-mandeb-strait-effectively-closed-by"
DEFAULT_OUTPUT = Path("bab_el_mandeb_9am_snapshot.csv")
DEFAULT_CHART_OUTPUT = Path("bab_el_mandeb_7_day_chart.html")
LABEL_COLUMN = "Deadline"


def selected_markets(
    markets: Iterable[dict[str, Any]], *, include_closed: bool = False
) -> list[dict[str, Any]]:
    """Return active event markets, excluding resolved deadlines by default."""
    return [
        market
        for market in markets
        if include_closed or not bool(market.get("closed"))
    ]


def deadline_sort_key(label: str) -> tuple[int, int, str]:
    """Sort labels such as 'July 31' in calendar order."""
    try:
        parsed = datetime.strptime(label, "%B %d")
    except ValueError:
        return (13, 32, label)
    return (parsed.month, parsed.day, label)


def create_chart(
    dates: list[str], series: dict[str, list[float | None]]
) -> Any:
    """Build a seven-day comparison of all tracked deadline markets."""
    import plotly.graph_objects as go

    labels = sorted(series, key=deadline_sort_key)
    colors = ["#2563EB", "#0891B2", "#D97706", "#7C3AED", "#DC2626"]
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
        title={
            "text": "Bab el-Mandeb Strait effectively closed by…?",
            "x": 0.5,
        },
        template="plotly_white",
        hovermode="x unified",
        xaxis={"title": "Daily snapshot at 9:00 AM ET", "type": "date"},
        yaxis={
            "title": "Yes probability (%)",
            "range": [0, 100],
            "ticksuffix": "%",
            "gridcolor": "#E5E7EB",
        },
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": 1.1},
        margin={"l": 70, "r": 35, "t": 120, "b": 90},
        annotations=[
            {
                "text": "Only currently open deadline markets are included by default.",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.2,
                "showarrow": False,
                "xanchor": "left",
                "font": {"size": 11, "color": "#4B5563"},
            },
            {
                "text": "Source: Polymarket Gamma and CLOB APIs",
                "xref": "paper",
                "yref": "paper",
                "x": 1,
                "y": -0.2,
                "showarrow": False,
                "xanchor": "right",
                "font": {"size": 11, "color": "#6B7280"},
            },
        ],
    )
    return figure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export daily Bab el-Mandeb market snapshots and create a seven-day chart."
        )
    )
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Polymarket event slug")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV output path")
    parser.add_argument(
        "--chart-output",
        type=Path,
        default=DEFAULT_CHART_OUTPUT,
        help="HTML chart output path",
    )
    parser.add_argument("--days", type=int, default=7, help="Calendar-day snapshots")
    parser.add_argument("--hour", type=int, default=9, help="Eastern snapshot hour")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="Include resolved deadline markets",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        targets = snapshot_targets(
            datetime.now(tz=ZoneInfo("UTC")), days=args.days, hour=args.hour
        )
    except ValueError as exc:
        logging.error("Invalid arguments: %s", exc)
        return 2

    session = build_session()
    try:
        event = fetch_event(session, args.slug, args.timeout)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        logging.error("Could not fetch event: %s", exc)
        return 1

    event_markets = event.get("markets", [])
    if not isinstance(event_markets, list):
        logging.error("The event returned an invalid markets list")
        return 1
    markets = selected_markets(event_markets, include_closed=args.include_closed)
    if not markets:
        logging.error("The event contains no markets matching the requested status")
        return 1

    logging.info("Fetching %d deadline markets", len(markets))
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
        dates, series = load_snapshot(args.output, label_column=LABEL_COLUMN)
        dates, series = latest_window(dates, series, args.days)
        figure = create_chart(dates, series)
        args.chart_output.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(
            args.chart_output,
            include_plotlyjs="cdn",
            full_html=True,
            config={"displaylogo": False, "responsive": True},
        )
    except (OSError, ValueError) as exc:
        logging.error("Could not create output: %s", exc)
        return 1

    logging.info(
        "Added %d new date(s); CSV contains %d rows at %s",
        added_dates,
        total_rows,
        args.output,
    )
    logging.info("Created chart at %s", args.chart_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
