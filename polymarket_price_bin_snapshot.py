#!/usr/bin/env python3
"""Reusable snapshot and chart workflow for Polymarket price-bin events."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from plot_wti_timeseries import create_chart, latest_window, load_snapshot
from polymarket_wti_snapshot import (
    build_session,
    collect_rows,
    fetch_event,
    merge_and_write_csv,
    snapshot_targets,
)


LABEL_COLUMN = "Price Bin"


def build_parser(
    *,
    description: str,
    default_slug: str,
    default_output: Path,
    default_chart_output: Path,
) -> argparse.ArgumentParser:
    """Create the shared command-line interface for a price-bin event."""
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
        "--exclude-closed",
        action="store_true",
        help="Exclude resolved price bins from the CSV and chart",
    )
    return parser


def run_tracker(args: argparse.Namespace) -> int:
    """Fetch, append, and chart one price-bin Polymarket event."""
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
    if not isinstance(event_markets, list) or not event_markets:
        logging.error("The event contains no markets")
        return 1
    markets = [
        market
        for market in event_markets
        if not args.exclude_closed or not bool(market.get("closed"))
    ]
    if not markets:
        logging.error("The event contains no markets matching the requested status")
        return 1

    logging.info("Fetching %d price bins", len(markets))
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
        dates, saved_series = load_snapshot(args.output, label_column=LABEL_COLUMN)
        dates, saved_series = latest_window(dates, saved_series, args.days)
        if args.exclude_closed:
            current_labels = {
                str(market.get("groupItemTitle") or market.get("question") or "Unknown market")
                for market in markets
            }
            series = {
                label: values
                for label, values in saved_series.items()
                if label in current_labels
            }
        else:
            series = saved_series
        event_title = str(event.get("title") or "Polymarket price-bin event")
        figure = create_chart(dates, series, title_prefix=event_title)
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
        "Added %d new date(s); CSV contains %d stored rows at %s",
        added_dates,
        total_rows,
        args.output,
    )
    logging.info("Created chart with %d price bins at %s", len(series), args.chart_output)
    return 0
