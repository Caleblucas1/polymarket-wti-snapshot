#!/usr/bin/env python3
"""Run a configured Polymarket tracker from the shared event registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from polymarket_deadline_snapshot import run_tracker as run_deadline_tracker
from polymarket_price_bin_snapshot import run_tracker as run_price_bin_tracker
from polymarket_wti_snapshot import run_snapshot


REGISTRY_PATH = Path(__file__).with_name("tracked_events.json")


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    """Load and minimally validate tracked event configuration."""
    with path.open(encoding="utf-8") as input_file:
        payload = json.load(input_file)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Event registry must contain at least one event")
    required = {"title", "engine", "slug", "output", "chart_output"}
    for key, config in payload.items():
        if not isinstance(config, dict) or not required.issubset(config):
            raise ValueError(f"Invalid event registry entry: {key}")
        if config["engine"] not in {"snapshot", "deadline", "price_bin"}:
            raise ValueError(f"Unsupported tracker engine for {key}: {config['engine']}")
    return payload


def run_event(
    event_key: str,
    *,
    data_dir: Path = Path("."),
    output: Path | None = None,
    chart_output: Path | None = None,
    slug: str | None = None,
    days: int = 7,
    hour: int = 9,
    timeout: float = 20,
    no_chart: bool = False,
    include_closed: bool = False,
    exclude_closed: bool = False,
) -> int:
    """Run one registry event through its configured tracking engine."""
    registry = load_registry()
    if event_key not in registry:
        raise ValueError(f"Unknown tracked event: {event_key}")
    config = registry[event_key]
    resolved_output = output or data_dir / str(config["output"])
    resolved_chart = chart_output or data_dir / str(config["chart_output"])
    args = argparse.Namespace(
        slug=slug or str(config["slug"]),
        output=resolved_output,
        chart_output=resolved_chart,
        days=days,
        hour=hour,
        timeout=timeout,
        no_chart=no_chart,
        include_closed=include_closed,
        exclude_closed=exclude_closed,
    )
    engine = config["engine"]
    if engine == "snapshot":
        return run_snapshot(args)
    if engine == "deadline":
        return run_deadline_tracker(args)
    return run_price_bin_tracker(args)


def build_parser() -> argparse.ArgumentParser:
    registry = load_registry()
    parser = argparse.ArgumentParser(description="Run a configured Polymarket tracker.")
    parser.add_argument("event", choices=sorted(registry), help="Configured event name")
    parser.add_argument("--data-dir", type=Path, default=Path("."), help="Output directory")
    parser.add_argument("--output", type=Path, help="Override CSV output path")
    parser.add_argument("--chart-output", type=Path, help="Override HTML output path")
    parser.add_argument("--slug", help="Override Polymarket event slug")
    parser.add_argument("--days", type=int, default=7, help="Calendar-day snapshots")
    parser.add_argument("--hour", type=int, default=9, help="Eastern snapshot hour")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    parser.add_argument("--no-chart", action="store_true", help="Update only the CSV")
    parser.add_argument("--include-closed", action="store_true", help="Include closed deadlines")
    parser.add_argument("--exclude-closed", action="store_true", help="Exclude closed price bins")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_event(
            args.event,
            data_dir=args.data_dir,
            output=args.output,
            chart_output=args.chart_output,
            slug=args.slug,
            days=args.days,
            hour=args.hour,
            timeout=args.timeout,
            no_chart=args.no_chart,
            include_closed=args.include_closed,
            exclude_closed=args.exclude_closed,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 2


def main_for_event(event_key: str) -> int:
    """Preserve an event-specific script as a compatibility entry point."""
    return main([event_key, *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
