#!/usr/bin/env python3
"""Safely migrate the legacy orderbook directory into the unified hierarchy."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from market_data_layout import MarketDataPaths


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migration_pairs(source: Path, destination: Path) -> list[tuple[Path, Path]]:
    layout = MarketDataPaths(destination)
    pairs = [
        (source / "market_instances.csv", layout.market_instances),
        (source / "logical_market_summary.csv", layout.logical_markets),
        (source / "market_lifecycle_events.csv", layout.lifecycle_events),
        (source / "orderbook_depth_snapshots.csv", layout.hourly_baseline),
        (source / "orderbook_depth_report.html", layout.report),
    ]
    for path in sorted((source / "depth").glob("orderbook_depth_*.csv")):
        month = path.stem.removeprefix("orderbook_depth_")
        pairs.append((path, layout.hourly / f"market_observations_{month}.csv"))
    return [(old, new) for old, new in pairs if old.exists()]


def migrate(source: Path, destination: Path, *, apply: bool = False) -> list[str]:
    pairs = migration_pairs(source, destination)
    if not pairs:
        return ["No legacy files found"]
    for old, new in pairs:
        if new.exists() and file_hash(old) != file_hash(new):
            raise ValueError(f"Refusing to overwrite different destination file: {new}")
    actions = [f"{old} -> {new}" for old, new in pairs]
    if not apply:
        return actions
    for old, new in pairs:
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            old.unlink()
        else:
            old.replace(new)
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("orderbook"))
    parser.add_argument("--destination", type=Path, default=Path("market_data"))
    parser.add_argument("--apply", action="store_true", help="Perform the verified moves")
    args = parser.parse_args()
    try:
        actions = migrate(args.source, args.destination, apply=args.apply)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    prefix = "Moved" if args.apply else "Would move"
    for action in actions:
        print(f"{prefix}: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
