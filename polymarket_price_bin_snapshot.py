#!/usr/bin/env python3
"""Reusable snapshot and chart workflow for Polymarket price-bin events."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from plot_wti_timeseries import write_chart
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
        range_path=getattr(args, "range_output", None),
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
        "--exclude-closed",
        action="store_true",
        help="Exclude resolved price bins from the CSV and chart",
    )
    return parser


def run_tracker(args: argparse.Namespace) -> TrackerResult:
    """Fetch, append, and chart one price-bin Polymarket event."""
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
        title = str(getattr(args, "title", "Polymarket price-bin event"))
        if not args.no_chart:
            try:
                series_count = write_price_bin_chart(args, title=title)
            except (OSError, ValueError) as exc:
                logging.error("Could not create chart: %s", exc)
                return TrackerResult("failed", exit_code=1)
            logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
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

    snapshot_markets = [
        market
        for market in event_markets
        if not event_closed and (not args.exclude_closed or not market_is_closed(market))
    ]
    if not event_closed and not snapshot_markets:
        logging.error("The event contains no markets matching the requested status")
        return TrackerResult("failed", exit_code=1)

    targets_by_date = {
        target.date().isoformat(): target
        for target in snapshot_targets_to_add + range_targets_to_add
    }
    targets = [targets_by_date[key] for key in sorted(targets_by_date)]
    rows = []
    range_rows = []
    if targets:
        history_markets = event_markets if range_targets_to_add else snapshot_markets
        logging.info("Fetching %d price bins for snapshots and ranges", len(history_markets))
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
            series_count = write_price_bin_chart(
                args,
                title=str(
                    event.get("title")
                    or getattr(args, "title", "Polymarket price-bin event")
                ),
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
        logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
    status = "closed" if event_closed else ("appended" if added_dates else "current")
    return TrackerResult(status, added_dates=added_dates, row_count=total_rows)
