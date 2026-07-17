#!/usr/bin/env python3
"""Snapshot Iran military-action contracts for Gulf-state dates."""

from __future__ import annotations

import argparse
from pathlib import Path

from polymarket_deadline_snapshot import build_parser, run_tracker


DEFAULT_SLUG = "iran-military-action-against-a-gulf-state-onptptpt-20260708212328295"
DEFAULT_OUTPUT = Path("iran_gulf_action_9am_snapshot.csv")
DEFAULT_CHART_OUTPUT = Path("iran_gulf_action_7_day_chart.html")


def parse_args() -> argparse.Namespace:
    parser = build_parser(
        description="Export daily Iran Gulf-action snapshots and a seven-day heatmap.",
        default_slug=DEFAULT_SLUG,
        default_output=DEFAULT_OUTPUT,
        default_chart_output=DEFAULT_CHART_OUTPUT,
    )
    return parser.parse_args()


def main() -> int:
    return run_tracker(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
