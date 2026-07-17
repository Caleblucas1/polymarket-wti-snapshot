#!/usr/bin/env python3
"""Snapshot and chart the Bab el-Mandeb effective-closure markets."""

from __future__ import annotations

import argparse
from pathlib import Path
from polymarket_deadline_snapshot import (
    build_parser,
    deadline_sort_key,
    run_tracker,
    selected_markets,
)


DEFAULT_SLUG = "bab-el-mandeb-strait-effectively-closed-by"
DEFAULT_OUTPUT = Path("bab_el_mandeb_9am_snapshot.csv")
DEFAULT_CHART_OUTPUT = Path("bab_el_mandeb_7_day_chart.html")
def parse_args() -> argparse.Namespace:
    parser = build_parser(
        description="Export daily Bab el-Mandeb snapshots and a seven-day chart.",
        default_slug=DEFAULT_SLUG,
        default_output=DEFAULT_OUTPUT,
        default_chart_output=DEFAULT_CHART_OUTPUT,
    )
    return parser.parse_args()


def main() -> int:
    return run_tracker(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
