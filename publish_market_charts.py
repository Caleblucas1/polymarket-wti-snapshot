#!/usr/bin/env python3
"""Publish immutable, freshness-verified copies of generated market charts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from track_market import load_registry


MANIFEST_NAME = "latest.json"


def latest_snapshot_date(path: Path) -> str:
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        header = next(csv.reader(input_file), [])
    dates = header[1:]
    if not dates:
        raise ValueError(f"Snapshot has no date columns: {path}")
    try:
        return max(datetime.strptime(value, "%Y-%m-%d").date() for value in dates).isoformat()
    except ValueError as exc:
        raise ValueError(f"Snapshot contains a non-ISO date column: {path}") from exc


def publish_chart(
    *, event_key: str, config: dict[str, Any], data_dir: Path, publish_dir: Path,
) -> dict[str, str]:
    snapshot_path = data_dir / str(config["output"])
    chart_path = data_dir / str(config["chart_output"])
    latest_date = latest_snapshot_date(snapshot_path)
    chart_bytes = chart_path.read_bytes()
    chart_text = chart_bytes.decode("utf-8")
    if latest_date not in chart_text:
        raise ValueError(
            f"Refusing to publish stale chart for {event_key}: "
            f"{latest_date} is absent from {chart_path}"
        )
    digest = hashlib.sha256(chart_bytes).hexdigest()
    filename = f"{chart_path.stem}_{latest_date}_{digest[:12]}.html"
    published_path = publish_dir / filename
    publish_dir.mkdir(parents=True, exist_ok=True)
    if published_path.exists():
        if published_path.read_bytes() != chart_bytes:
            raise ValueError(f"Content-address collision at {published_path}")
    else:
        temporary = published_path.with_suffix(".html.tmp")
        temporary.write_bytes(chart_bytes)
        temporary.replace(published_path)
    return {
        "event": event_key,
        "source_latest_date": latest_date,
        "source_chart": str(chart_path),
        "published_chart": str(published_path),
        "sha256": digest,
    }


def publish_all_charts(
    data_dir: Path,
    *,
    event_keys: Iterable[str] | None = None,
    publish_dir: Path | None = None,
    registry: dict[str, dict[str, Any]] | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    registry = registry or load_registry()
    selected = list(event_keys) if event_keys is not None else list(registry)
    destination = publish_dir or data_dir / "published_charts"
    entries = [
        publish_chart(
            event_key=event_key,
            config=registry[event_key],
            data_dir=data_dir,
            publish_dir=destination,
        )
        for event_key in selected
    ]
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rule": "Only surface published_chart paths; filenames change whenever chart bytes change.",
        "charts": entries,
    }
    manifest_path = destination / MANIFEST_NAME
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest_path, entries


def main() -> int:
    registry = load_registry()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("."))
    parser.add_argument("--publish-dir", type=Path)
    parser.add_argument("--events", nargs="+", choices=sorted(registry), default=list(registry))
    args = parser.parse_args()
    try:
        manifest_path, entries = publish_all_charts(
            args.data_dir,
            event_keys=args.events,
            publish_dir=args.publish_dir,
            registry=registry,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"chart-manifest: {manifest_path}")
    for entry in entries:
        print(f"{entry['event']}: {entry['published_chart']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
