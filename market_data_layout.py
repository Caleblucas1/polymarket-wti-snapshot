#!/usr/bin/env python3
"""Canonical paths and integrity checks for the shared market-data hierarchy."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "2"


@dataclass(frozen=True)
class MarketDataPaths:
    """All non-daily market data below one explicit root."""

    root: Path

    @property
    def event_catalog(self) -> Path:
        return self.root / "catalog" / "events.csv"

    @property
    def market_instances(self) -> Path:
        return self.root / "catalog" / "market_instances.csv"

    @property
    def logical_markets(self) -> Path:
        return self.root / "catalog" / "logical_market_summary.csv"

    @property
    def lifecycle_events(self) -> Path:
        return self.root / "lifecycle" / "market_lifecycle_events.csv"

    @property
    def hourly(self) -> Path:
        return self.root / "hourly"

    @property
    def hourly_baseline(self) -> Path:
        return self.hourly / "market_observations_baseline.csv"

    @property
    def report(self) -> Path:
        return self.root / "reports" / "market_liquidity_report.html"


EVENT_CATALOG_FIELDS = [
    "Schema Version", "Event Key", "Event Slug", "Engine", "Snapshot Path",
    "Range Path", "Chart Path", "Snapshot Grain", "Range Window", "Timezone",
]


def event_catalog_rows(registry: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Describe daily compatibility outputs without duplicating their data."""
    validate_registry(registry)
    return [
        {
            "Schema Version": SCHEMA_VERSION,
            "Event Key": event_key,
            "Event Slug": str(config["slug"]),
            "Engine": str(config["engine"]),
            "Snapshot Path": str(config["output"]),
            "Range Path": str(config["range_output"]),
            "Chart Path": str(config["chart_output"]),
            "Snapshot Grain": "logical-market x 9am-Eastern day",
            "Range Window": "trailing 24 hours ending at 9am Eastern",
            "Timezone": "America/New_York",
        }
        for event_key, config in sorted(registry.items())
    ]


def validate_registry(registry: dict[str, dict[str, Any]]) -> None:
    """Reject missing fields and path collisions before any collection writes."""
    required = {"slug", "engine", "output", "range_output", "chart_output"}
    if not registry:
        raise ValueError("Tracked-event registry is empty")
    seen_slugs: dict[str, str] = {}
    seen_paths: dict[str, tuple[str, str]] = {}
    for event_key, config in registry.items():
        missing = sorted(required - config.keys())
        if missing:
            raise ValueError(f"{event_key} is missing registry fields: {', '.join(missing)}")
        slug = str(config["slug"])
        if slug in seen_slugs:
            raise ValueError(f"Event slug collision: {event_key} and {seen_slugs[slug]}")
        seen_slugs[slug] = event_key
        for field in ("output", "range_output", "chart_output"):
            value = str(config[field])
            prior = seen_paths.get(value)
            if prior:
                raise ValueError(
                    f"Output path collision: {event_key}.{field} and {prior[0]}.{prior[1]} use {value}"
                )
            seen_paths[value] = (event_key, field)


def write_event_catalog(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=EVENT_CATALOG_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(event_catalog_rows(registry))
    temporary.replace(path)


def validate_daily_compatibility_files(project_root: Path, registry: dict[str, dict[str, Any]]) -> list[str]:
    """Validate daily grains without changing any existing compatibility CSV."""
    errors: list[str] = []
    for event_key, config in registry.items():
        snapshot_path = project_root / str(config["output"])
        if snapshot_path.exists():
            with snapshot_path.open(newline="", encoding="utf-8-sig") as input_file:
                reader = csv.reader(input_file)
                header = next(reader, [])
                dates = header[1:]
                if len(dates) != len(set(dates)):
                    errors.append(f"{event_key}: duplicate snapshot date column")
                if any(len(value) != 10 or value[4] != "-" or value[7] != "-" for value in dates):
                    errors.append(f"{event_key}: snapshot columns must be ISO dates")
        range_path = project_root / str(config["range_output"])
        if range_path.exists():
            with range_path.open(newline="", encoding="utf-8-sig") as input_file:
                reader = csv.DictReader(input_file)
                rows = list(reader)
                label_fields = [
                    field for field in (reader.fieldnames or [])
                    if field not in {"Date", "Low", "High"}
                ]
            label_field = label_fields[0] if len(label_fields) == 1 else ""
            if not label_field:
                errors.append(f"{event_key}: range file needs exactly one market-label column")
            keys: set[tuple[str, str]] = set()
            for row in rows:
                key = (row.get(label_field, ""), row.get("Date", ""))
                if key in keys:
                    errors.append(f"{event_key}: duplicate range key {key}")
                keys.add(key)
                try:
                    low = float(row.get("Low", ""))
                    high = float(row.get("High", ""))
                except (TypeError, ValueError):
                    continue
                if low > high:
                    errors.append(f"{event_key}: range low exceeds high for {key}")
    return errors


def write_dataset_manifest(path: Path) -> None:
    """Document authority and derivation so readers cannot confuse data grains."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "authority": {
            "daily_snapshots": "repository-root *_9am_snapshot.csv files",
            "daily_ranges": "repository-root *_9am_ranges.csv files",
            "hourly_market_observations": "hourly/market_observations_YYYY-MM.csv partitions",
            "market_instances": "catalog/market_instances.csv",
            "logical_markets": "catalog/logical_market_summary.csv",
            "lifecycle_events": "lifecycle/market_lifecycle_events.csv",
        },
        "derivations": {
            "daily_snapshot": "latest CLOB price-history sample at or before 9am Eastern",
            "daily_range": "minimum and maximum five-minute CLOB samples in the trailing 24-hour window ending at 9am Eastern",
            "hourly_reference_probability": "book midpoint when two-sided; otherwise Gamma last-trade probability",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
