#!/usr/bin/env python3
"""Maintain a durable inventory of Polymarket UMA resolution and dispute status."""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from polymarket_wti_snapshot import build_session, fetch_event, parse_json_array


DEFAULT_OUTPUT = "market_resolution_status.csv"
FIELDNAMES = [
    "Event Key",
    "Event Title",
    "Market",
    "Condition ID",
    "Current Status",
    "Currently Disputed",
    "Ever Disputed",
    "Dispute Count",
    "Status History",
    "Closed",
    "Automatically Resolved",
    "First Seen",
    "Last Checked",
]


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _status_history(market: dict[str, Any]) -> list[str]:
    return [
        str(status).strip().lower()
        for status in parse_json_array(market.get("umaResolutionStatuses"))
        if str(status).strip()
    ]


def status_rows(
    event_key: str,
    configured_title: str,
    event: dict[str, Any],
    *,
    checked_at: datetime,
) -> list[dict[str, str]]:
    """Convert one Gamma event into normalized market status records."""
    markets = event.get("markets", [])
    if not isinstance(markets, list):
        raise ValueError(f"Event {event_key} contains an invalid markets field")
    timestamp = checked_at.astimezone(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    event_title = str(event.get("title") or configured_title)
    rows: list[dict[str, str]] = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        label = str(
            market.get("groupItemTitle")
            or market.get("question")
            or "Unknown market"
        )
        history = _status_history(market)
        current = str(market.get("umaResolutionStatus") or "").strip().lower()
        if not current and history:
            current = history[-1]
        dispute_count = sum(status == "disputed" for status in history)
        rows.append(
            {
                "Event Key": event_key,
                "Event Title": event_title,
                "Market": label,
                "Condition ID": str(market.get("conditionId") or ""),
                "Current Status": current,
                "Currently Disputed": "true" if current == "disputed" else "false",
                "Ever Disputed": "true" if dispute_count else "false",
                "Dispute Count": str(dispute_count),
                "Status History": " > ".join(history),
                "Closed": "true" if _truthy(market.get("closed")) else "false",
                "Automatically Resolved": (
                    "true" if _truthy(market.get("automaticallyResolved")) else "false"
                ),
                "First Seen": timestamp,
                "Last Checked": timestamp,
            }
        )
    return rows


def _row_key(row: dict[str, str]) -> tuple[str, str]:
    condition_id = str(row.get("Condition ID") or "").strip()
    fallback = str(row.get("Market") or "").strip()
    return str(row.get("Event Key") or "").strip(), condition_id or fallback


def merge_status_rows(
    existing_rows: list[dict[str, str]],
    incoming_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Refresh current fields while keeping a sticky record of past disputes."""
    rows_by_key = {_row_key(row): dict(row) for row in existing_rows}
    for incoming in incoming_rows:
        key = _row_key(incoming)
        existing = rows_by_key.get(key)
        if existing is None:
            rows_by_key[key] = dict(incoming)
            continue
        merged = dict(existing)
        merged.update(incoming)
        merged["First Seen"] = existing.get("First Seen") or incoming["First Seen"]
        existing_disputes = int(existing.get("Dispute Count") or 0)
        incoming_disputes = int(incoming.get("Dispute Count") or 0)
        merged["Dispute Count"] = str(max(existing_disputes, incoming_disputes))
        merged["Ever Disputed"] = (
            "true"
            if existing.get("Ever Disputed") == "true"
            or incoming.get("Ever Disputed") == "true"
            else "false"
        )
        if len(existing.get("Status History") or "") > len(incoming.get("Status History") or ""):
            merged["Status History"] = existing["Status History"]
        rows_by_key[key] = merged
    return sorted(
        rows_by_key.values(),
        key=lambda row: (row.get("Event Key", ""), row.get("Market", "")),
    )


def write_status_csv(path: Path, incoming_rows: list[dict[str, str]]) -> tuple[int, int]:
    """Atomically write the merged status inventory and return change statistics."""
    existing_rows: list[dict[str, str]] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as input_file:
            reader = csv.DictReader(input_file)
            if not reader.fieldnames or not set(FIELDNAMES).issubset(reader.fieldnames):
                raise ValueError("Existing resolution-status CSV has an incompatible schema")
            existing_rows = [
                {field: str(row.get(field) or "") for field in FIELDNAMES}
                for row in reader
            ]
    merged_rows = merge_status_rows(existing_rows, incoming_rows)
    existing_by_key = {_row_key(row): row for row in existing_rows}
    changed = sum(existing_by_key.get(_row_key(row)) != row for row in merged_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged_rows)
    temporary_path.replace(path)
    return changed, len(merged_rows)


def refresh_resolution_status(
    registry: dict[str, dict[str, Any]],
    *,
    data_dir: Path,
    timeout: float,
    workers: int = 4,
    now: datetime | None = None,
) -> tuple[int, int, list[str]]:
    """Fetch every configured event and refresh one consolidated status CSV."""
    checked_at = now or datetime.now(tz=ZoneInfo("UTC"))

    def fetch_one(event_key: str, config: dict[str, Any]) -> list[dict[str, str]]:
        session = build_session()
        event = fetch_event(session, str(config["slug"]), timeout)
        return status_rows(
            event_key,
            str(config["title"]),
            event,
            checked_at=checked_at,
        )

    incoming_rows: list[dict[str, str]] = []
    failures: list[str] = []
    worker_count = min(max(1, workers), len(registry))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(fetch_one, event_key, config): event_key
            for event_key, config in registry.items()
        }
        for future in as_completed(futures):
            event_key = futures[future]
            try:
                incoming_rows.extend(future.result())
            except (requests.RequestException, OSError, ValueError) as exc:
                failures.append(f"{event_key}: {exc}")

    changed, total = write_status_csv(data_dir / DEFAULT_OUTPUT, incoming_rows)
    return changed, total, failures
