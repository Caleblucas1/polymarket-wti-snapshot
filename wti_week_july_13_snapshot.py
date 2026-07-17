#!/usr/bin/env python3
"""Snapshot WTI price-bin contracts for the week of July 13, 2026."""

from __future__ import annotations

import argparse
from pathlib import Path

from polymarket_price_bin_snapshot import build_parser, run_tracker


DEFAULT_SLUG = "will-wti-hit-week-of-july-13-2026"
DEFAULT_OUTPUT = Path("wti_week_july_13_9am_snapshot.csv")
DEFAULT_CHART_OUTPUT = Path("wti_week_july_13_7_day_chart.html")


def parse_args() -> argparse.Namespace:
    parser = build_parser(
        description="Export WTI week-of-July-13 snapshots and a seven-day chart.",
        default_slug=DEFAULT_SLUG,
        default_output=DEFAULT_OUTPUT,
        default_chart_output=DEFAULT_CHART_OUTPUT,
    )
    return parser.parse_args()


def main() -> int:
    return run_tracker(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
