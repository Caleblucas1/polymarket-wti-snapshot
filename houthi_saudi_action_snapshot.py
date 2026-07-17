#!/usr/bin/env python3
"""Snapshot Houthi military-action contracts against Saudi Arabia."""

from __future__ import annotations

import argparse
from pathlib import Path

from polymarket_deadline_snapshot import build_parser, run_tracker


DEFAULT_SLUG = "houthi-military-action-against-saudi-arabia-byptptpt-20260714212508550"
DEFAULT_OUTPUT = Path("houthi_saudi_action_9am_snapshot.csv")
DEFAULT_CHART_OUTPUT = Path("houthi_saudi_action_7_day_chart.html")


def parse_args() -> argparse.Namespace:
    parser = build_parser(
        description="Export daily Houthi-Saudi action snapshots and a seven-day chart.",
        default_slug=DEFAULT_SLUG,
        default_output=DEFAULT_OUTPUT,
        default_chart_output=DEFAULT_CHART_OUTPUT,
    )
    return parser.parse_args()


def main() -> int:
    return run_tracker(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
