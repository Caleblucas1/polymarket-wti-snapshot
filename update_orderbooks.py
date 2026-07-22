#!/usr/bin/env python3
"""Update the independent order-book depth and market-lifecycle schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from polymarket_orderbook import run_orderbook_update


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect order-book depth for all tracked events.")
    parser.add_argument("--data-dir", type=Path, default=Path("orderbook"))
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--workers", type=int, default=7)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.workers < 1:
        print("Error: workers must be at least 1")
        return 2
    try:
        result = run_orderbook_update(
            args.data_dir, timeout=args.timeout, workers=args.workers
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
