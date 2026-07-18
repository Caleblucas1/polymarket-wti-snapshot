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

from plot_wti_timeseries import write_chart
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


LABEL_COLUMN = "Price Bin"


def write_price_bin_chart(
    args: argparse.Namespace,
    *,
    title: str,
    labels: set[str] | None = None,
) -> int:
    """Render a price-bin chart directly from its cumulative CSV."""
    return write_chart(
        args.output,
        args.chart_output,
        days=args.days,
        label_column=LABEL_COLUMN,
        title_prefix=title,
        labels=labels,
    )


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
        "--no-chart",
        action="store_true",
        help="Update only the CSV and skip HTML chart generation",
    )
    parser.add_argument(
        "--exclude-closed",
        action="store_true",
        help="Exclude resolved price bins from the CSV and chart",
    )
    return parser


def run_tracker(args: argparse.Namespace) -> TrackerResult:
    """Fetch, append, and chart one price-bin Polymarket event."""
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
        labels = None
        title = str(getattr(args, "title", "Polymarket price-bin event"))
        if args.exclude_closed:
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
                    else [market for market in event_markets if not market_is_closed(market)]
                )
                labels = {
                    str(market.get("groupItemTitle") or market.get("question") or "Unknown market")
                    for market in chart_markets
                }
                title = str(event.get("title") or title)
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                logging.error("Could not fetch event for chart filters: %s", exc)
                return TrackerResult("failed", exit_code=1)
        else:
            logging.info("All requested snapshot dates already exist; no API calls were needed")
            event_closed = False
        try:
            series_count = write_price_bin_chart(args, title=title, labels=labels)
        except (OSError, ValueError) as exc:
            logging.error("Could not create chart: %s", exc)
            return TrackerResult("failed", exit_code=1)
        logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
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
                series_count = write_price_bin_chart(
                    args,
                    title=str(
                        event.get("title")
                        or getattr(args, "title", "Polymarket price-bin event")
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
            logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
        return TrackerResult("closed")
    markets = [
        market
        for market in event_markets
        if not args.exclude_closed or not market_is_closed(market)
    ]
    if not markets:
        logging.error("The event contains no markets matching the requested status")
        return TrackerResult("failed", exit_code=1)

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
        series_count = 0
        if not args.no_chart:
            series_count = write_price_bin_chart(
                args,
                title=str(
                    event.get("title")
                    or getattr(args, "title", "Polymarket price-bin event")
                ),
                labels=(
                    {
                        str(
                            market.get("groupItemTitle")
                            or market.get("question")
                            or "Unknown market"
                        )
                        for market in markets
                    }
                    if args.exclude_closed
                    else None
                ),
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
        logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
    status = "appended" if added_dates else "current"
    return TrackerResult(status, added_dates=added_dates, row_count=total_rows)
