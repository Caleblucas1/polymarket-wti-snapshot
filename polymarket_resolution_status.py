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
DEFAULT_EVENTS_OUTPUT = "market_resolution_events.csv"
BASE_FIELDNAMES = [
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
FIELDNAMES = [
    *BASE_FIELDNAMES,
    "Condition Created At",
    "Resolved At",
    "Current Yes Probability",
    "Resolved Outcome",
    "Yes Resolution Probability",
]
BASE_EVENT_FIELDNAMES = [
    "Observed At",
    "Event Key",
    "Event Title",
    "Market",
    "Condition ID",
    "Event Type",
    "Previous Status",
    "Current Status",
    "Dispute Count",
]
EVENT_FIELDNAMES = [
    *BASE_EVENT_FIELDNAMES,
    "Resolved At",
    "Resolved Outcome",
    "Yes Resolution Probability",
    "Automatically Resolved",
    "Resolution Details",
]


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _status_history(market: dict[str, Any]) -> list[str]:
    return [
        str(status).strip().lower()
        for status in parse_json_array(market.get("umaResolutionStatuses"))
        if str(status).strip()
    ]


def _outcome_state(
    market: dict[str, Any],
    current: str,
) -> tuple[str, str, str]:
    """Return current Yes probability plus terminal outcome fields."""
    outcomes = [str(value).strip() for value in parse_json_array(market.get("outcomes"))]
    raw_prices = parse_json_array(market.get("outcomePrices"))
    if not outcomes or len(raw_prices) != len(outcomes):
        return "", "", ""
    try:
        prices = [float(value) for value in raw_prices]
    except (TypeError, ValueError):
        return "", "", ""
    yes_index = next(
        (index for index, outcome in enumerate(outcomes) if outcome.lower() == "yes"),
        None,
    )
    current_yes_probability = (
        "" if yes_index is None else f"{prices[yes_index] * 100:.1f}"
    )
    if current != "resolved" and not _truthy(market.get("closed")):
        return current_yes_probability, "", ""
    winner_index = max(range(len(prices)), key=prices.__getitem__)
    if prices[winner_index] < 0.99:
        return current_yes_probability, "", ""
    return current_yes_probability, outcomes[winner_index], current_yes_probability


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
        (
            current_yes_probability,
            resolved_outcome,
            yes_probability,
        ) = _outcome_state(market, current)
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
                "Condition Created At": str(market.get("createdAt") or ""),
                "Resolved At": str(
                    market.get("closedTime")
                    or market.get("umaEndDate")
                    or ""
                ),
                "Current Yes Probability": current_yes_probability,
                "Resolved Outcome": resolved_outcome,
                "Yes Resolution Probability": yes_probability,
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
        for field in (
            "Condition Created At",
            "Resolved At",
            "Current Yes Probability",
            "Resolved Outcome",
            "Yes Resolution Probability",
        ):
            if not merged.get(field):
                merged[field] = existing.get(field, "")
        rows_by_key[key] = merged
    return sorted(
        rows_by_key.values(),
        key=lambda row: (row.get("Event Key", ""), row.get("Market", "")),
    )


def read_status_csv(path: Path) -> list[dict[str, str]]:
    """Read either the original or extended resolution-status schema."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames or not set(BASE_FIELDNAMES).issubset(reader.fieldnames):
            raise ValueError("Existing resolution-status CSV has an incompatible schema")
        return [
            {field: str(row.get(field) or "") for field in FIELDNAMES}
            for row in reader
        ]


def write_status_csv(path: Path, incoming_rows: list[dict[str, str]]) -> tuple[int, int]:
    """Atomically write the merged status inventory and return change statistics."""
    existing_rows = read_status_csv(path)
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


def resolution_transition_events(
    existing_rows: list[dict[str, str]],
    incoming_rows: list[dict[str, str]],
    *,
    observed_at: datetime,
) -> list[dict[str, str]]:
    """Return newly observed dispute and resolution transitions."""
    timestamp = observed_at.astimezone(ZoneInfo("America/New_York")).isoformat(
        timespec="seconds"
    )
    existing_by_key = {_row_key(row): row for row in existing_rows}
    events: list[dict[str, str]] = []
    for incoming in incoming_rows:
        existing = existing_by_key.get(_row_key(incoming))
        previous = str((existing or {}).get("Current Status") or "").strip().lower()
        current = str(incoming.get("Current Status") or "").strip().lower()
        previous_disputes = int((existing or {}).get("Dispute Count") or 0)
        current_disputes = int(incoming.get("Dispute Count") or 0)
        event_types: list[str] = []
        if current_disputes > previous_disputes:
            event_types.append("dispute-detected")
        if existing is not None and previous != "resolved" and current == "resolved":
            event_types.append("resolved")
        elif previous == "disputed" and current != "disputed":
            event_types.append("dispute-cleared")
        for event_type in event_types:
            resolution_details = ""
            if event_type == "resolved":
                outcome = incoming.get("Resolved Outcome", "") or "unknown outcome"
                yes_probability = incoming.get("Yes Resolution Probability", "")
                resolved_at = incoming.get("Resolved At", "")
                automatic = incoming.get("Automatically Resolved", "")
                detail_parts = [f"outcome={outcome}"]
                if yes_probability:
                    detail_parts.append(f"yes_probability={yes_probability}")
                if resolved_at:
                    detail_parts.append(f"resolved_at={resolved_at}")
                if automatic:
                    detail_parts.append(f"automatically_resolved={automatic}")
                resolution_details = "; ".join(detail_parts)
            events.append(
                {
                    "Observed At": timestamp,
                    "Event Key": incoming.get("Event Key", ""),
                    "Event Title": incoming.get("Event Title", ""),
                    "Market": incoming.get("Market", ""),
                    "Condition ID": incoming.get("Condition ID", ""),
                    "Event Type": event_type,
                    "Previous Status": previous,
                    "Current Status": current,
                    "Dispute Count": str(current_disputes),
                    "Resolved At": incoming.get("Resolved At", ""),
                    "Resolved Outcome": incoming.get("Resolved Outcome", ""),
                    "Yes Resolution Probability": incoming.get("Yes Resolution Probability", ""),
                    "Automatically Resolved": incoming.get("Automatically Resolved", ""),
                    "Resolution Details": resolution_details,
                }
            )
    return events


def bootstrap_current_dispute_events(
    existing_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Seed currently active disputes when adopting the event log."""
    events: list[dict[str, str]] = []
    for row in existing_rows:
        if str(row.get("Currently Disputed") or "").lower() != "true":
            continue
        events.append(
            {
                "Observed At": row.get("Last Checked") or row.get("First Seen", ""),
                "Event Key": row.get("Event Key", ""),
                "Event Title": row.get("Event Title", ""),
                "Market": row.get("Market", ""),
                "Condition ID": row.get("Condition ID", ""),
                "Event Type": "dispute-detected",
                "Previous Status": "unknown",
                "Current Status": "disputed",
                "Dispute Count": row.get("Dispute Count", "0"),
                "Resolved At": "",
                "Resolved Outcome": "",
                "Yes Resolution Probability": "",
                "Automatically Resolved": "",
                "Resolution Details": "",
            }
        )
    return events


def append_resolution_events(
    path: Path,
    events: list[dict[str, str]],
) -> tuple[int, int]:
    """Append unique resolution lifecycle events without revising history."""
    existing_rows: list[dict[str, str]] = []
    existing_keys: set[tuple[str, str, str, str]] = set()
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as input_file:
            reader = csv.DictReader(input_file)
            if not reader.fieldnames or not set(BASE_EVENT_FIELDNAMES).issubset(
                reader.fieldnames
            ):
                raise ValueError("Existing resolution-events CSV has an incompatible schema")
            for row in reader:
                normalized = {
                    field: str(row.get(field) or "") for field in EVENT_FIELDNAMES
                }
                existing_rows.append(normalized)
                existing_keys.add(
                    (
                        normalized["Observed At"],
                        normalized["Event Key"],
                        normalized["Condition ID"] or normalized["Market"],
                        normalized["Event Type"],
                    )
                )
    new_rows: list[dict[str, str]] = []
    for event in events:
        normalized = {field: str(event.get(field) or "") for field in EVENT_FIELDNAMES}
        key = (
            normalized["Observed At"],
            normalized["Event Key"],
            normalized["Condition ID"] or normalized["Market"],
            normalized["Event Type"],
        )
        if key in existing_keys:
            continue
        existing_keys.add(key)
        new_rows.append(normalized)
    if not new_rows:
        return 0, len(existing_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=EVENT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(existing_rows + new_rows)
    temporary_path.replace(path)
    return len(new_rows), len(existing_rows) + len(new_rows)


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

    status_path = data_dir / DEFAULT_OUTPUT
    existing_rows = read_status_csv(status_path)
    events_path = data_dir / DEFAULT_EVENTS_OUTPUT
    events = (
        bootstrap_current_dispute_events(existing_rows)
        if not events_path.exists()
        else []
    )
    events.extend(resolution_transition_events(
        existing_rows,
        incoming_rows,
        observed_at=checked_at,
    ))
    changed, total = write_status_csv(status_path, incoming_rows)
    append_resolution_events(events_path, events)
    return changed, total, failures
