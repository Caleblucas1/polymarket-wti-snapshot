#!/usr/bin/env python3
"""Update configured Polymarket events concurrently."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from polymarket_resolution_status import refresh_resolution_status
from polymarket_wti_snapshot import TrackerResult
from plot_related_markets import DEFAULT_OUTPUT as RELATED_MARKET_CHART
from plot_related_markets import write_related_market_chart
from track_market import load_registry, run_event


def build_parser() -> argparse.ArgumentParser:
    registry = load_registry()
    all_events = list(registry)
    parser = argparse.ArgumentParser(description="Update multiple tracked markets concurrently.")
    parser.add_argument(
        "--events",
        nargs="+",
        choices=sorted(registry),
        default=all_events,
        help="Events to update; defaults to every configured market",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("."), help="CSV directory")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent event workers")
    parser.add_argument("--days", type=int, default=7, help="Calendar-day snapshots")
    parser.add_argument("--hour", type=int, default=9, help="Eastern snapshot hour")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    parser.add_argument(
        "--with-charts",
        action="store_true",
        help="Generate each event chart; CSV-only is the default",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.workers < 1:
        print("Error: workers must be at least 1")
        return 2

    results: dict[str, TrackerResult] = {}
    worker_count = min(args.workers, len(args.events))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                run_event,
                event_key,
                data_dir=args.data_dir,
                days=args.days,
                hour=args.hour,
                timeout=args.timeout,
                no_chart=not args.with_charts,
            ): event_key
            for event_key in args.events
        }
        for future in as_completed(futures):
            event_key = futures[future]
            try:
                results[event_key] = future.result()
            except Exception as exc:  # Keep other independent updates running.
                print(f"{event_key}: failed: {exc}")
                results[event_key] = TrackerResult("failed", exit_code=1)

    for event_key in args.events:
        result = results.get(event_key, TrackerResult("failed", exit_code=1))
        if result.status == "appended":
            detail = f"appended {result.added_dates} date(s)"
        elif result.status == "current":
            detail = "already current"
        elif result.status == "closed":
            detail = "fully closed"
        else:
            detail = "failed"
        print(f"{event_key}: {detail}")

    status_failures: list[str] = []
    if not args.with_charts:
        registry = load_registry()
        selected_registry = {key: registry[key] for key in args.events}
        try:
            changed, total, status_failures = refresh_resolution_status(
                selected_registry,
                data_dir=args.data_dir,
                timeout=args.timeout,
                workers=args.workers,
            )
            print(
                "resolution-status: "
                f"refreshed {total} markets ({changed} changed or newly discovered)"
            )
            for failure in status_failures:
                print(f"resolution-status: failed: {failure}")
        except (OSError, ValueError) as exc:
            status_failures = [str(exc)]
            print(f"resolution-status: failed: {exc}")
    elif set(args.events) == set(load_registry()):
        try:
            count = write_related_market_chart(
                data_dir=args.data_dir,
                output=args.data_dir / RELATED_MARKET_CHART,
                days=args.days,
            )
            print(f"related-markets: wrote {count} comparison(s)")
        except (OSError, ValueError) as exc:
            status_failures = [str(exc)]
            print(f"related-markets: failed: {exc}")
    return (
        1
        if any(result.exit_code != 0 for result in results.values()) or status_failures
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
