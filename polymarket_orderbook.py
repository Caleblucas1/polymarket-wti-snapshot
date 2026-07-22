#!/usr/bin/env python3
"""Collect Polymarket order-book depth and track physical market lifecycles."""

from __future__ import annotations

import csv
import html
import json
import logging
import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

from polymarket_wti_snapshot import build_session, fetch_event, parse_json_array
from track_market import load_registry


CLOB_BOOKS_URL = "https://clob.polymarket.com/books"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"
BOOK_BATCH_LIMIT = 20
DEPTH_BANDS = (0.01, 0.02, 0.05, 0.10)
EFFECTIVE_DEPTH_HALF_LIFE = 0.01

INSTANCE_FIELDS = [
    "Event Key", "Event Slug", "Logical Market ID", "Threshold Family ID",
    "Market Label", "Direction", "Threshold", "Condition ID", "Yes Token ID",
    "No Token ID", "Market ID", "Question", "Created At", "First Seen",
    "Last Seen", "Present", "Active", "Closed", "Accepting Orders",
    "Order Book Enabled", "Instance Number", "Replaces Condition ID", "Volume",
    "Volume 24h", "Liquidity", "Last Trade Price",
]

LIFECYCLE_FIELDS = [
    "Detected At", "Event Key", "Logical Market ID", "Threshold Family ID",
    "Market Label", "Event Type", "Condition ID", "Related Condition ID", "Details",
]

DEPTH_FIELDS = [
    "Snapshot At", "Hour ET", "Session", "Book Timestamp", "Event Key", "Event Slug",
    "Logical Market ID", "Threshold Family ID", "Market Label", "Condition ID",
    "Token ID", "Outcome", "Book Status", "Best Bid", "Best Ask", "Midpoint",
    "Spread", "Bid Levels", "Ask Levels", "Bid Shares Total", "Ask Shares Total",
    "Bid Notional Total", "Ask Notional Total", "Bid Shares 1c", "Ask Shares 1c",
    "Bid Notional 1c", "Ask Notional 1c", "Bid Shares 2c", "Ask Shares 2c",
    "Bid Notional 2c", "Ask Notional 2c", "Bid Shares 5c", "Ask Shares 5c",
    "Bid Notional 5c", "Ask Notional 5c", "Bid Shares 10c", "Ask Shares 10c",
    "Bid Notional 10c", "Ask Notional 10c", "Book Hash", "Instance Volume",
    "Logical Lifetime Volume", "Liquidity", "Last Trade Price", "Weak Side Notional 2c",
    "Weak Side Notional 5c", "Book Imbalance 5c", "Bid Effective Notional",
    "Ask Effective Notional", "Weak Side Effective Notional",
]

SUMMARY_FIELDS = [
    "Event Key", "Logical Market ID", "Threshold Family ID", "Market Label",
    "Direction", "Threshold", "Physical Instance Count", "Present Instance Count",
    "Current Condition ID", "Condition IDs", "First Seen", "Last Seen",
    "Logical Lifetime Volume", "Current Liquidity", "Current Last Trade Price",
]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bool_text(value: Any) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() == "true" else "false"
    return "true" if bool(value) else "false"


def is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.10f}".rstrip("0").rstrip(".")


def float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def session_for_timestamp(timestamp: str) -> tuple[str, str]:
    """Return Eastern hour and a mutually exclusive global-liquidity session."""
    observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    hour = observed.astimezone(ZoneInfo("America/New_York")).hour
    if 3 <= hour < 9:
        session = "Europe (03–09 ET)"
    elif 9 <= hour < 17:
        session = "U.S. (09–17 ET)"
    elif 20 <= hour or hour < 3:
        session = "Asia (20–03 ET)"
    else:
        session = "Evening (17–20 ET)"
    return str(hour), session


def market_label(market: dict[str, Any]) -> str:
    return str(market.get("groupItemTitle") or market.get("question") or "Unknown market").strip()


def normalized_contract_label(label: str) -> tuple[str, str, str]:
    """Return normalized semantics, direction, and numeric threshold."""
    compact = " ".join(label.strip().split())
    lowered = compact.lower()
    direction = ""
    if compact.startswith("↑") or " high " in f" {lowered} ":
        direction = "up"
    elif compact.startswith("↓") or " low " in f" {lowered} ":
        direction = "down"
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", compact)
    raw_threshold = match.group(1) if match else ""
    threshold = (
        raw_threshold.rstrip("0").rstrip(".")
        if "." in raw_threshold
        else raw_threshold
    )
    normalized = lowered.replace("↑", " up ").replace("↓", " down ")
    normalized = re.sub(r"[^a-z0-9.]+", "-", normalized).strip("-")
    return normalized or "unknown", direction, threshold


def logical_ids(event_key: str, label: str) -> tuple[str, str, str, str]:
    normalized, direction, threshold = normalized_contract_label(label)
    logical_id = f"{event_key}::{normalized}"
    family_id = f"{event_key}::threshold-{threshold}" if threshold else logical_id
    return logical_id, family_id, direction, threshold


def outcome_tokens(market: dict[str, Any]) -> tuple[str, str]:
    token_ids = [str(value) for value in parse_json_array(market.get("clobTokenIds"))]
    outcomes = [str(value).strip().lower() for value in parse_json_array(market.get("outcomes"))]
    yes_token = ""
    no_token = ""
    for index, outcome in enumerate(outcomes):
        if index >= len(token_ids):
            continue
        if outcome == "yes":
            yes_token = token_ids[index]
        elif outcome == "no":
            no_token = token_ids[index]
    if not yes_token and token_ids:
        yes_token = token_ids[0]
    if not no_token and len(token_ids) > 1:
        no_token = token_ids[1]
    return yes_token, no_token


def instance_from_market(
    event_key: str, event_slug: str, market: dict[str, Any], detected_at: str
) -> dict[str, str]:
    label = market_label(market)
    logical_id, family_id, direction, threshold = logical_ids(event_key, label)
    yes_token, no_token = outcome_tokens(market)
    return {
        "Event Key": event_key,
        "Event Slug": event_slug,
        "Logical Market ID": logical_id,
        "Threshold Family ID": family_id,
        "Market Label": label,
        "Direction": direction,
        "Threshold": threshold,
        "Condition ID": str(market.get("conditionId") or ""),
        "Yes Token ID": yes_token,
        "No Token ID": no_token,
        "Market ID": str(market.get("id") or ""),
        "Question": str(market.get("question") or ""),
        "Created At": str(market.get("createdAt") or ""),
        "First Seen": detected_at,
        "Last Seen": detected_at,
        "Present": "true",
        "Active": bool_text(market.get("active")),
        "Closed": bool_text(market.get("closed")),
        "Accepting Orders": bool_text(market.get("acceptingOrders")),
        "Order Book Enabled": bool_text(market.get("enableOrderBook")),
        "Instance Number": "1",
        "Replaces Condition ID": "",
        "Volume": number_text(market.get("volumeNum", market.get("volume"))),
        "Volume 24h": number_text(market.get("volume24hr")),
        "Liquidity": number_text(market.get("liquidityNum", market.get("liquidity"))),
        "Last Trade Price": number_text(market.get("lastTradePrice")),
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return [dict(row) for row in csv.DictReader(input_file)]


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file, fieldnames=fields, extrasaction="ignore", lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def lifecycle_event(
    instance: dict[str, str], event_type: str, detected_at: str,
    *, related: str = "", details: str = "",
) -> dict[str, str]:
    return {
        "Detected At": detected_at,
        "Event Key": instance["Event Key"],
        "Logical Market ID": instance["Logical Market ID"],
        "Threshold Family ID": instance["Threshold Family ID"],
        "Market Label": instance["Market Label"],
        "Event Type": event_type,
        "Condition ID": instance["Condition ID"],
        "Related Condition ID": related,
        "Details": details,
    }


def reconcile_instances(
    existing: list[dict[str, str]], current: list[dict[str, str]], detected_at: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Update the physical-instance inventory and emit one-time lifecycle transitions."""
    by_condition = {row["Condition ID"]: dict(row) for row in existing if row.get("Condition ID")}
    previously_present = {
        condition_id for condition_id, row in by_condition.items() if is_true(row.get("Present"))
    }
    seen: set[str] = set()
    events: list[dict[str, str]] = []

    for incoming in current:
        condition_id = incoming["Condition ID"]
        if not condition_id:
            continue
        seen.add(condition_id)
        prior = by_condition.get(condition_id)
        if prior is None:
            exact = [
                row for row in by_condition.values()
                if row.get("Logical Market ID") == incoming["Logical Market ID"]
            ]
            family = [
                row for row in by_condition.values()
                if row.get("Threshold Family ID") == incoming["Threshold Family ID"]
                and row.get("Logical Market ID") != incoming["Logical Market ID"]
            ]
            incoming = dict(incoming)
            incoming["Instance Number"] = str(
                1 + max((int(row.get("Instance Number") or 1) for row in exact), default=0)
            )
            if exact:
                replaced = sorted(exact, key=lambda row: row.get("Created At") or row.get("First Seen") or "")[-1]
                incoming["Replaces Condition ID"] = replaced["Condition ID"]
                events.append(lifecycle_event(
                    incoming, "replaced", detected_at,
                    related=replaced["Condition ID"],
                    details="New physical condition for the same logical contract",
                ))
            elif family:
                related = sorted(family, key=lambda row: row.get("Created At") or row.get("First Seen") or "")[-1]
                events.append(lifecycle_event(
                    incoming, "related-threshold-appeared", detected_at,
                    related=related["Condition ID"],
                    details="Same numeric threshold but different direction or proposition; not stitched",
                ))
            else:
                events.append(lifecycle_event(incoming, "appeared", detected_at))
            by_condition[condition_id] = incoming
            continue

        updated = dict(prior)
        for field in INSTANCE_FIELDS:
            if field not in {"First Seen", "Instance Number", "Replaces Condition ID"}:
                updated[field] = incoming.get(field, updated.get(field, ""))
        updated["First Seen"] = prior.get("First Seen") or detected_at
        updated["Instance Number"] = prior.get("Instance Number") or "1"
        updated["Replaces Condition ID"] = prior.get("Replaces Condition ID") or ""
        transitions = [
            ("Closed", "closed", "reopened"),
            ("Accepting Orders", "orders-opened", "orders-stopped"),
            ("Order Book Enabled", "orderbook-enabled", "orderbook-disabled"),
        ]
        for field, true_event, false_event in transitions:
            before = is_true(prior.get(field))
            after = is_true(updated.get(field))
            if before != after:
                event_type = true_event if after else false_event
                events.append(lifecycle_event(updated, event_type, detected_at))
        by_condition[condition_id] = updated

    for condition_id in previously_present - seen:
        row = by_condition[condition_id]
        row["Present"] = "false"
        events.append(lifecycle_event(
            row, "disappeared", detected_at,
            details="Condition no longer returned in its configured Gamma event",
        ))

    rows = sorted(
        by_condition.values(),
        key=lambda row: (
            row.get("Event Key", ""), row.get("Logical Market ID", ""),
            int(row.get("Instance Number") or 1), row.get("Condition ID", ""),
        ),
    )
    return rows, events


def fetch_all_markets(
    session: requests.Session, timeout: float, workers: int
) -> list[tuple[str, str, dict[str, Any]]]:
    registry = load_registry()
    collected: list[tuple[str, str, dict[str, Any]]] = []

    def fetch_one(item: tuple[str, dict[str, Any]]) -> tuple[str, str, list[dict[str, Any]]]:
        event_key, config = item
        slug = str(config["slug"])
        event = fetch_event(session, slug, timeout)
        markets = event.get("markets", [])
        if not isinstance(markets, list):
            raise ValueError(f"Unexpected market list for {event_key}")
        return event_key, slug, markets

    with ThreadPoolExecutor(max_workers=min(workers, len(registry))) as executor:
        futures = {executor.submit(fetch_one, item): item[0] for item in registry.items()}
        for future in as_completed(futures):
            event_key, slug, markets = future.result()
            collected.extend((event_key, slug, market) for market in markets)
    return sorted(collected, key=lambda item: (item[0], market_label(item[2])))


def parse_levels(values: Any) -> list[tuple[float, float]]:
    levels: list[tuple[float, float]] = []
    if not isinstance(values, list):
        return levels
    for value in values:
        try:
            price = float(value["price"])
            size = float(value["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(price) and math.isfinite(size) and size >= 0:
            levels.append((price, size))
    return levels


def summarize_book(book: dict[str, Any]) -> dict[str, str]:
    bids = parse_levels(book.get("bids"))
    asks = parse_levels(book.get("asks"))
    best_bid = max((price for price, _ in bids), default=None)
    best_ask = min((price for price, _ in asks), default=None)
    midpoint = (
        (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
    )
    summary = {
        "Book Timestamp": str(book.get("timestamp") or ""),
        "Best Bid": number_text(best_bid),
        "Best Ask": number_text(best_ask),
        "Midpoint": number_text(midpoint),
        "Spread": number_text(best_ask - best_bid if best_bid is not None and best_ask is not None else None),
        "Bid Levels": str(len(bids)),
        "Ask Levels": str(len(asks)),
        "Bid Shares Total": number_text(sum(size for _, size in bids)),
        "Ask Shares Total": number_text(sum(size for _, size in asks)),
        "Bid Notional Total": number_text(sum(price * size for price, size in bids)),
        "Ask Notional Total": number_text(sum(price * size for price, size in asks)),
        "Book Hash": str(book.get("hash") or ""),
    }
    for band in DEPTH_BANDS:
        suffix = f"{int(band * 100)}c"
        near_bids = [
            (price, size) for price, size in bids
            if best_bid is not None and price >= best_bid - band - 1e-12
        ]
        near_asks = [
            (price, size) for price, size in asks
            if best_ask is not None and price <= best_ask + band + 1e-12
        ]
        summary[f"Bid Shares {suffix}"] = number_text(sum(size for _, size in near_bids))
        summary[f"Ask Shares {suffix}"] = number_text(sum(size for _, size in near_asks))
        summary[f"Bid Notional {suffix}"] = number_text(sum(price * size for price, size in near_bids))
        summary[f"Ask Notional {suffix}"] = number_text(sum(price * size for price, size in near_asks))
    summary["Bid Effective Notional"] = number_text(sum(
        price * size * (0.5 ** ((best_bid - price) / EFFECTIVE_DEPTH_HALF_LIFE))
        for price, size in bids
    ) if best_bid is not None else 0)
    summary["Ask Effective Notional"] = number_text(sum(
        price * size * (0.5 ** ((price - best_ask) / EFFECTIVE_DEPTH_HALF_LIFE))
        for price, size in asks
    ) if best_ask is not None else 0)
    return summary


def fetch_books(
    session: requests.Session, token_ids: list[str], timeout: float
) -> dict[str, dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for start in range(0, len(token_ids), BOOK_BATCH_LIMIT):
        chunk = token_ids[start : start + BOOK_BATCH_LIMIT]
        try:
            response = session.post(
                CLOB_BOOKS_URL,
                json=[{"token_id": token_id} for token_id in chunk],
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("CLOB books response was not a list")
            for book in payload:
                if isinstance(book, dict) and book.get("asset_id"):
                    books[str(book["asset_id"])] = book
            continue
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            logging.warning("Batch order-book request failed; using individual requests: %s", exc)
        for token_id in chunk:
            try:
                response = session.get(
                    CLOB_BOOK_URL, params={"token_id": token_id}, timeout=timeout
                )
                response.raise_for_status()
                book = response.json()
                if isinstance(book, dict):
                    books[token_id] = book
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                logging.warning("No order book for token %s: %s", token_id, exc)
    return books


def logical_volume_totals(instances: Iterable[dict[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in instances:
        try:
            totals[row["Logical Market ID"]] += float(row.get("Volume") or 0)
        except (TypeError, ValueError):
            continue
    return dict(totals)


def collect_depth_rows(
    session: requests.Session, instances: list[dict[str, str]], snapshot_at: str, timeout: float
) -> list[dict[str, str]]:
    present = [row for row in instances if is_true(row.get("Present"))]
    eligible = [
        row for row in present
        if row.get("Yes Token ID") and is_true(row.get("Order Book Enabled"))
        and is_true(row.get("Accepting Orders")) and not is_true(row.get("Closed"))
    ]
    books = fetch_books(session, [row["Yes Token ID"] for row in eligible], timeout)
    lifetime_volume = logical_volume_totals(instances)
    hour_et, session_name = session_for_timestamp(snapshot_at)
    rows: list[dict[str, str]] = []
    for instance in present:
        token_id = instance.get("Yes Token ID", "")
        if is_true(instance.get("Closed")):
            status = "closed"
        elif not is_true(instance.get("Order Book Enabled")):
            status = "disabled"
        elif not is_true(instance.get("Accepting Orders")):
            status = "not-accepting-orders"
        elif token_id not in books:
            status = "unavailable"
        else:
            status = "available"
        row = {field: "" for field in DEPTH_FIELDS}
        row.update({
            "Snapshot At": snapshot_at,
            "Hour ET": hour_et,
            "Session": session_name,
            "Event Key": instance["Event Key"],
            "Event Slug": instance["Event Slug"],
            "Logical Market ID": instance["Logical Market ID"],
            "Threshold Family ID": instance["Threshold Family ID"],
            "Market Label": instance["Market Label"],
            "Condition ID": instance["Condition ID"],
            "Token ID": token_id,
            "Outcome": "Yes",
            "Book Status": status,
            "Instance Volume": instance.get("Volume", ""),
            "Logical Lifetime Volume": number_text(lifetime_volume.get(instance["Logical Market ID"])),
            "Liquidity": instance.get("Liquidity", ""),
            "Last Trade Price": instance.get("Last Trade Price", ""),
        })
        if status == "available":
            row.update(summarize_book(books[token_id]))
            bid_2c = float_value(row.get("Bid Notional 2c"))
            ask_2c = float_value(row.get("Ask Notional 2c"))
            bid_5c = float_value(row.get("Bid Notional 5c"))
            ask_5c = float_value(row.get("Ask Notional 5c"))
            total_5c = bid_5c + ask_5c
            row["Weak Side Notional 2c"] = number_text(min(bid_2c, ask_2c))
            row["Weak Side Notional 5c"] = number_text(min(bid_5c, ask_5c))
            row["Book Imbalance 5c"] = number_text(
                (bid_5c - ask_5c) / total_5c if total_5c else None
            )
            row["Weak Side Effective Notional"] = number_text(min(
                float_value(row.get("Bid Effective Notional")),
                float_value(row.get("Ask Effective Notional")),
            ))
        rows.append(row)
    return rows


def build_logical_summary(instances: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in instances:
        grouped[row["Logical Market ID"]].append(row)
    totals = logical_volume_totals(instances)
    summaries: list[dict[str, str]] = []
    for logical_id, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: (int(row.get("Instance Number") or 1), row.get("Created At", "")))
        present = [row for row in ordered if is_true(row.get("Present"))]
        current = present[-1] if present else ordered[-1]
        summaries.append({
            "Event Key": current["Event Key"],
            "Logical Market ID": logical_id,
            "Threshold Family ID": current["Threshold Family ID"],
            "Market Label": current["Market Label"],
            "Direction": current.get("Direction", ""),
            "Threshold": current.get("Threshold", ""),
            "Physical Instance Count": str(len(ordered)),
            "Present Instance Count": str(len(present)),
            "Current Condition ID": current["Condition ID"],
            "Condition IDs": "|".join(row["Condition ID"] for row in ordered),
            "First Seen": min(row.get("First Seen", "") for row in ordered),
            "Last Seen": max(row.get("Last Seen", "") for row in ordered),
            "Logical Lifetime Volume": number_text(totals.get(logical_id)),
            "Current Liquidity": current.get("Liquidity", ""),
            "Current Last Trade Price": current.get("Last Trade Price", ""),
        })
    return summaries


def append_depth(path: Path, rows: list[dict[str, str]]) -> None:
    existing = read_csv(path)
    for row in existing:
        if row.get("Snapshot At") and not row.get("Session"):
            row["Hour ET"], row["Session"] = session_for_timestamp(row["Snapshot At"])
        bid_5c = float_value(row.get("Bid Notional 5c"))
        ask_5c = float_value(row.get("Ask Notional 5c"))
        total_5c = bid_5c + ask_5c
        if row.get("Book Status") == "available":
            row["Weak Side Notional 5c"] = number_text(min(bid_5c, ask_5c))
            row["Book Imbalance 5c"] = number_text(
                (bid_5c - ask_5c) / total_5c if total_5c else None
            )
    keys = {
        (row.get("Snapshot At", ""), row.get("Condition ID", ""), row.get("Token ID", ""))
        for row in existing
    }
    new_rows = [
        row for row in rows
        if (row["Snapshot At"], row["Condition ID"], row["Token ID"]) not in keys
    ]
    write_csv(path, DEPTH_FIELDS, [*existing, *new_rows])


def depth_partition_path(data_dir: Path, snapshot_at: str) -> Path:
    """Keep hourly history in bounded monthly files instead of one ever-growing CSV."""
    month = snapshot_at[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError(f"Invalid snapshot timestamp: {snapshot_at}")
    return data_dir / "depth" / f"orderbook_depth_{month}.csv"


def read_depth_history(data_dir: Path) -> list[dict[str, str]]:
    """Read the pre-partition baseline plus every monthly depth partition."""
    paths = [
        data_dir / "orderbook_depth_snapshots.csv",
        *sorted((data_dir / "depth").glob("orderbook_depth_*.csv")),
    ]
    rows: list[dict[str, str]] = []
    keys: set[tuple[str, str, str]] = set()
    for path in paths:
        for row in read_csv(path):
            key = (
                row.get("Snapshot At", ""), row.get("Condition ID", ""),
                row.get("Token ID", ""),
            )
            if key not in keys:
                rows.append(row)
                keys.add(key)
    return rows


def write_report(path: Path, rows: list[dict[str, str]], lifecycle: list[dict[str, str]]) -> None:
    import plotly.graph_objects as go

    if not rows:
        raise ValueError("No order-book snapshots are available to report")
    latest_at = max(row.get("Snapshot At", "") for row in rows)
    latest = [row for row in rows if row.get("Snapshot At") == latest_at]
    available = [row for row in latest if row.get("Book Status") == "available"]
    historical_available = [row for row in rows if row.get("Book Status") == "available"]

    depth_rows = sorted(
        available, key=lambda row: (row.get("Event Key", ""), row.get("Market Label", "")),
    )
    depth_labels = [f"{row['Event Key']} · {row['Market Label']}" for row in depth_rows]
    bid_effective = [float_value(row.get("Bid Effective Notional")) for row in depth_rows]
    ask_effective = [float_value(row.get("Ask Effective Notional")) for row in depth_rows]
    bid_notional = [float_value(row.get("Bid Notional 5c")) for row in depth_rows]
    ask_notional = [float_value(row.get("Ask Notional 5c")) for row in depth_rows]
    bid_shares = [float_value(row.get("Bid Shares 5c")) for row in depth_rows]
    ask_shares = [float_value(row.get("Ask Shares 5c")) for row in depth_rows]
    depth_customdata = [[
        float_value(row.get("Bid Notional 5c")),
        float_value(row.get("Ask Notional 5c")),
        float_value(row.get("Bid Shares 5c")),
        float_value(row.get("Ask Shares 5c")),
        float_value(row.get("Instance Volume")),
        float_value(row.get("Logical Lifetime Volume")),
        float_value(row.get("Bid Effective Notional")),
        float_value(row.get("Ask Effective Notional")),
    ] for row in depth_rows]
    depth_figure = go.Figure()
    depth_figure.add_trace(go.Bar(
        x=bid_effective, y=depth_labels, orientation="h",
        name="BLUE — effective bid support (distance-weighted dollars)",
        marker={"color": "#2563EB"}, customdata=depth_customdata,
        hovertemplate=(
            "<b>%{y}</b><br>Effective bid-side depth: $%{customdata[6]:,.2f}"
            "<br>Raw bid-side dollars within 5 points: $%{customdata[0]:,.2f}"
            "<br>Bid-side shares within 5 points: %{customdata[2]:,.0f}"
            "<br>Current-listing volume: $%{customdata[4]:,.0f}"
            "<br>Continuous-market volume: $%{customdata[5]:,.0f}<extra></extra>"
        ),
    ))
    depth_figure.add_trace(go.Bar(
        x=ask_effective, y=depth_labels, orientation="h",
        name="RED — effective ask resistance (distance-weighted dollars)",
        marker={"color": "#DC2626"}, customdata=depth_customdata,
        hovertemplate=(
            "<b>%{y}</b><br>Effective ask-side depth: $%{customdata[7]:,.2f}"
            "<br>Raw ask-side dollars within 5 points: $%{customdata[1]:,.2f}"
            "<br>Ask-side shares within 5 points: %{customdata[3]:,.0f}"
            "<br>Current-listing volume: $%{customdata[4]:,.0f}"
            "<br>Continuous-market volume: $%{customdata[5]:,.0f}<extra></extra>"
        ),
    ))
    depth_figure.add_trace(go.Bar(
        x=bid_notional, y=depth_labels, orientation="h", visible=False,
        name="BLUE — raw bid dollars within 5 points",
        marker={"color": "#2563EB"}, customdata=depth_customdata,
        hovertemplate=(
            "<b>%{y}</b><br>Bid-side dollars within 5 points: $%{customdata[0]:,.2f}"
            "<br>Bid-side shares within 5 points: %{customdata[2]:,.0f}<extra></extra>"
        ),
    ))
    depth_figure.add_trace(go.Bar(
        x=ask_notional, y=depth_labels, orientation="h", visible=False,
        name="RED — raw ask dollars within 5 points",
        marker={"color": "#DC2626"}, customdata=depth_customdata,
        hovertemplate=(
            "<b>%{y}</b><br>Ask-side dollars within 5 points: $%{customdata[1]:,.2f}"
            "<br>Ask-side shares within 5 points: %{customdata[3]:,.0f}<extra></extra>"
        ),
    ))
    depth_figure.add_trace(go.Bar(
        x=bid_shares, y=depth_labels, orientation="h", visible=False,
        name="BLUE — raw bid shares within 5 points",
        marker={"color": "#2563EB"}, customdata=depth_customdata,
        hovertemplate=(
            "<b>%{y}</b><br>Bid-side shares within 5 points: %{customdata[2]:,.0f}"
            "<br>Bid-side dollars within 5 points: $%{customdata[0]:,.2f}<extra></extra>"
        ),
    ))
    depth_figure.add_trace(go.Bar(
        x=ask_shares, y=depth_labels, orientation="h", visible=False,
        name="RED — raw ask shares within 5 points",
        marker={"color": "#DC2626"}, customdata=depth_customdata,
        hovertemplate=(
            "<b>%{y}</b><br>Ask-side shares within 5 points: %{customdata[3]:,.0f}"
            "<br>Ask-side dollars within 5 points: $%{customdata[1]:,.2f}<extra></extra>"
        ),
    ))
    depth_figure.update_layout(
        title={"text": "Resting liquidity within five probability points of each best quote", "x": 0.5},
        template="plotly_white", barmode="group", height=max(900, 31 * len(depth_rows)),
        xaxis={"title": "Effective resting depth ($, exponentially distance-weighted)"},
        yaxis={"title": ""},
        legend={"orientation": "h", "y": 1.075, "x": 0},
        margin={"l": 245, "r": 40, "t": 125, "b": 85},
        updatemenus=[{
            "type": "buttons", "direction": "right", "x": 0, "y": 1.12,
            "buttons": [
                {"label": "Effective dollars", "method": "update", "args": [
                    {"visible": [True, True, False, False, False, False]},
                    {"xaxis.title.text": "Effective resting depth ($, exponentially distance-weighted)"},
                ]},
                {"label": "Raw 5pt dollars", "method": "update", "args": [
                    {"visible": [False, False, True, True, False, False]},
                    {"xaxis.title.text": "Price-weighted resting notional ($)"},
                ]},
                {"label": "Raw 5pt shares", "method": "update", "args": [
                    {"visible": [False, False, False, False, True, True]},
                    {"xaxis.title.text": "Resting outcome-token shares"},
                ]},
            ],
        }],
    )

    easiest = sorted(
        available,
        key=lambda row: float_value(row.get("Weak Side Effective Notional")),
    )[:25]
    easiest.reverse()
    move_values = [float_value(row.get("Weak Side Effective Notional")) for row in easiest]
    # A zero value is economically meaningful: one side has no displayed depth.
    # Plot it at a small visual floor so it remains visible on the logarithmic axis.
    move_plot_values = [max(value, 0.10) for value in move_values]
    move_figure = go.Figure(go.Bar(
        x=move_plot_values,
        y=[f"{row['Event Key']} · {row['Market Label']}" for row in easiest],
        orientation="h",
        marker={"color": "#D97706", "line": {"color": "#92400E", "width": 1}},
        text=["one-sided ($0)" if value == 0 else f"${value:,.0f}" for value in move_values],
        textposition="outside",
        customdata=[[
            float_value(row.get("Ask Notional 5c")),
            float_value(row.get("Bid Notional 5c")),
            float_value(row.get("Spread")) * 100,
            float_value(row.get("Book Imbalance 5c")),
            row.get("Best Bid", ""), row.get("Best Ask", ""),
            float_value(row.get("Weak Side Effective Notional")),
        ] for row in easiest],
        hovertemplate=(
            "<b>%{y}</b><br>Weaker-side effective depth: $%{customdata[6]:,.2f}"
            "<br>Cost to lift asks through +5 points: $%{customdata[0]:,.0f}"
            "<br>Bid notional through −5 points: $%{customdata[1]:,.0f}"
            "<br>Spread: %{customdata[2]:.2f} points"
            "<br>5-point imbalance: %{customdata[3]:+.1%}"
            "<br>Best bid / ask: %{customdata[4]} / %{customdata[5]}<extra></extra>"
        ),
    ))
    move_figure.update_layout(
        title={"text": "Markets with the least nearby effective liquidity", "x": 0.5},
        template="plotly_white", height=max(650, 31 * len(easiest)), showlegend=False,
        xaxis={"title": "Weaker-side effective depth ($, log scale)", "type": "log"},
        yaxis={"title": ""}, margin={"l": 235, "r": 95, "t": 85, "b": 75},
        annotations=[{
            "text": "One-sided books have $0 displayed resistance and use a $0.10 visual floor.",
            "xref": "paper", "yref": "paper", "x": 0, "y": -0.13,
            "showarrow": False, "font": {"size": 11, "color": "#6B7280"},
        }],
    )

    palette = ["#2563EB", "#D97706", "#7C3AED", "#0891B2", "#DB2777", "#4F46E5", "#059669"]
    confidence_figure = go.Figure()
    events = sorted({row["Event Key"] for row in available})
    max_volume = max((float_value(row.get("Instance Volume")) for row in available), default=1)
    for index, event_key in enumerate(events):
        event_rows = [
            row for row in available
            if row["Event Key"] == event_key and float_value(row.get("Weak Side Effective Notional")) > 0
        ]
        confidence_figure.add_trace(go.Scatter(
            x=[float_value(row.get("Spread")) * 100 for row in event_rows],
            y=[float_value(row.get("Weak Side Effective Notional")) for row in event_rows],
            mode="markers", name=event_key,
            marker={
                "color": palette[index % len(palette)], "opacity": 0.78,
                "size": [8 + 28 * math.sqrt(float_value(row.get("Instance Volume")) / max_volume) for row in event_rows],
                "line": {"color": "#111827", "width": 0.7},
            },
            text=[row["Market Label"] for row in event_rows],
            customdata=[[
                row.get("Best Bid", ""), row.get("Best Ask", ""),
                float_value(row.get("Weak Side Notional 5c")),
                float_value(row.get("Instance Volume")),
            ] for row in event_rows],
            hovertemplate=(
                "<b>%{text}</b><br>Spread: %{x:.2f} points"
                "<br>Weaker-side effective depth: $%{y:,.0f}"
                "<br>Weakest-side depth within 5 points: $%{customdata[2]:,.0f}"
                "<br>Best bid / ask: %{customdata[0]} / %{customdata[1]}"
                "<br>Current-listing volume: $%{customdata[3]:,.0f}<extra>%{fullData.name}</extra>"
            ),
        ))
    confidence_figure.update_layout(
        title={"text": "Displayed-price credibility: spread versus executable two-sided depth", "x": 0.5},
        template="plotly_white", height=650,
        xaxis={"title": "Bid–ask spread (probability points)", "rangemode": "tozero"},
        yaxis={"title": "Weaker-side effective depth ($, log scale)", "type": "log"},
        legend={"orientation": "h", "y": 1.12},
        margin={"l": 80, "r": 35, "t": 115, "b": 75},
    )

    session_order = ["Asia (20–03 ET)", "Europe (03–09 ET)", "U.S. (09–17 ET)", "Evening (17–20 ET)"]
    session_values: list[float] = []
    session_samples: list[int] = []
    session_observations: list[int] = []
    for session_name in session_order:
        session_rows = [
            row for row in historical_available
            if (row.get("Session") or session_for_timestamp(row["Snapshot At"])[1]) == session_name
            and float_value(row.get("Weak Side Effective Notional")) > 0
        ]
        session_values.append(median([
            float_value(row["Weak Side Effective Notional"]) for row in session_rows
        ]) if session_rows else 0)
        session_samples.append(len({row["Snapshot At"] for row in session_rows}))
        session_observations.append(len(session_rows))
    session_figure = go.Figure(go.Bar(
        x=session_order, y=session_values,
        marker={"color": ["#7C3AED", "#0891B2", "#2563EB", "#D97706"]},
        text=[f"${value:,.0f}<br>{samples} samples" for value, samples in zip(session_values, session_samples)],
        textposition="outside",
        customdata=[[samples, observations] for samples, observations in zip(session_samples, session_observations)],
        hovertemplate=(
            "<b>%{x}</b><br>Median weaker-side effective depth: $%{y:,.0f}"
            "<br>Book snapshots: %{customdata[0]}"
            "<br>Market observations: %{customdata[1]}<extra></extra>"
        ),
    ))
    session_figure.update_layout(
        title={"text": "When liquidity is thickest", "x": 0.5},
        template="plotly_white", height=520, showlegend=False,
        xaxis={"title": "Mutually exclusive Eastern-time session"},
        yaxis={"title": "Median weaker-side effective depth ($)", "rangemode": "tozero"},
        margin={"l": 85, "r": 35, "t": 85, "b": 90},
    )

    config = {"displaylogo": False, "responsive": True}
    depth_plot = depth_figure.to_html(include_plotlyjs="cdn", full_html=False, config=config)
    move_plot = move_figure.to_html(include_plotlyjs=False, full_html=False, config=config)
    confidence_plot = confidence_figure.to_html(include_plotlyjs=False, full_html=False, config=config)
    session_plot = session_figure.to_html(include_plotlyjs=False, full_html=False, config=config)
    table_columns = [
        ("Event Key", "Event"), ("Market Label", "Market"), ("Book Status", "Status"),
        ("Spread", "Spread (points)"), ("Bid Shares 5c", "Bid shares, 5pt"),
        ("Bid Notional 5c", "Bid dollars, 5pt"), ("Ask Shares 5c", "Ask shares, 5pt"),
        ("Ask Notional 5c", "Ask dollars, 5pt"),
        ("Bid Effective Notional", "Effective bid dollars"),
        ("Ask Effective Notional", "Effective ask dollars"),
        ("Weak Side Effective Notional", "Weaker-side effective dollars"),
        ("Weak Side Notional 5c", "Weaker-side dollars, 5pt"),
        ("Book Imbalance 5c", "Imbalance, 5pt"),
        ("Instance Volume", "Current-listing volume"),
        ("Logical Lifetime Volume", "Continuous-market volume"),
    ]

    def table_value(row: dict[str, str], field: str) -> str:
        value = row.get(field, "")
        if value in {"", None}:
            return ""
        if field == "Spread":
            return f"{float_value(value) * 100:,.2f}"
        if field == "Book Imbalance 5c":
            return f"{float_value(value):+.1%}"
        if "Notional" in field or "Volume" in field:
            return f"${float_value(value):,.2f}"
        if "Shares" in field:
            return f"{float_value(value):,.0f}"
        return str(value)

    table_rows = []
    for row in sorted(latest, key=lambda value: (value["Event Key"], value["Market Label"])):
        table_rows.append("<tr>" + "".join(
            f"<td>{html.escape(table_value(row, field))}</td>"
            for field, _ in table_columns
        ) + "</tr>")
    lifecycle_rows = []
    for row in lifecycle[-100:]:
        lifecycle_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(row.get(field, '')))}</td>"
            for field in ["Detected At", "Event Key", "Market Label", "Event Type", "Condition ID", "Related Condition ID"]
        ) + "</tr>")
    available_count = len(available)
    easiest_row = min(available, key=lambda row: float_value(row.get("Weak Side Effective Notional")), default={})
    resilient_row = max(available, key=lambda row: float_value(row.get("Weak Side Effective Notional")), default={})
    distinct_snapshots = len({row.get("Snapshot At") for row in rows})
    easiest_value = float_value(easiest_row.get("Weak Side Effective Notional"))
    resilient_value = float_value(resilient_row.get("Weak Side Effective Notional"))
    raw_resilient_value = float_value(resilient_row.get("Weak Side Notional 5c"))
    easiest_display = "one-sided ($0)" if easiest_row and easiest_value == 0 else f"${easiest_value:,.0f}"
    session_note = (
        "Session comparisons are preliminary. At least 8–12 snapshots spanning multiple sessions are needed before treating the pattern as evidence."
        if distinct_snapshots < 8 or sum(value > 0 for value in session_values) < 2
        else "Session bars use the median across all available market observations in each Eastern-time window."
    )
    document = f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Polymarket liquidity and market impact</title><style>body{{font-family:Arial,sans-serif;margin:24px;color:#111827;background:#f9fafb}}main{{max-width:1500px;margin:auto}}.hero,.panel,.card{{background:white;border:1px solid #e5e7eb;border-radius:12px}}.hero{{padding:22px;margin-bottom:18px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}}.card{{padding:14px}}.kpi{{font-size:24px;font-weight:700;margin-top:6px}}.label,.note{{font-size:12px;color:#6b7280}}.panel{{padding:12px;margin:18px 0}}table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:16px;background:white}}th,td{{border:1px solid #d1d5db;padding:6px;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}th{{background:#f3f4f6;position:sticky;top:0}}.scroll{{overflow:auto;max-height:720px}}p,li{{color:#4b5563;line-height:1.45}}@media(max-width:800px){{.grid{{grid-template-columns:1fr 1fr}}body{{margin:8px}}}}</style></head><body><main><section class=\"hero\"><h1>Polymarket liquidity and market impact</h1><p>Latest book: {html.escape(latest_at)}. The dashboard measures executable Yes-token liquidity—not just displayed probability.</p><div class=\"grid\"><div class=\"card\"><div class=\"label\">Available books</div><div class=\"kpi\">{available_count}</div></div><div class=\"card\"><div class=\"label\">Easiest current 5-point move</div><div class=\"kpi\">{easiest_display}</div><div class=\"note\">{html.escape(str(easiest_row.get('Event Key','')))} · {html.escape(str(easiest_row.get('Market Label','')))}</div></div><div class=\"card\"><div class=\"label\">Most resilient current 5-point book</div><div class=\"kpi\">${float_value(resilient_row.get('Weak Side Notional 5c')):,.0f}</div><div class=\"note\">{html.escape(str(resilient_row.get('Event Key','')))} · {html.escape(str(resilient_row.get('Market Label','')))}</div></div><div class=\"card\"><div class=\"label\">Intraday snapshots collected</div><div class=\"kpi\">{distinct_snapshots}</div></div></div><ul><li><b>Blue</b> is resting bid liquidity: buyers supporting the price against a downward move.</li><li><b>Red</b> is resting ask liquidity: sellers resisting an upward move.</li><li><b>Shares</b> count outcome tokens; <b>dollar notional</b> is the sum of price × shares and better represents economic depth.</li><li><b>Physical-instance volume</b> covers the current Polymarket condition only; <b>logical-lifetime volume</b> sums genuine replacement instances of the same event and market.</li></ul></section><section class=\"panel\">{depth_plot}<p>Use the buttons above the chart to switch between dollars and shares. At very low probabilities, a huge share count can represent modest dollar value; if the best bid is below five cents, this band can also include almost the full bid book.</p></section><section class=\"panel\">{move_plot}<p>Lower bars are easier to push: the metric is the smaller of ask notional through +5 points and bid notional through −5 points. A one-sided book has no displayed resistance in one direction. This is an order-book estimate, not a guarantee against cancellations or hidden liquidity.</p></section><section class=\"panel\">{confidence_plot}<p>Stronger displayed prices sit toward the upper-left: narrower spreads and more executable liquidity on the weaker side. Bubble size reflects physical-instance traded volume.</p></section><section class=\"panel\">{session_plot}<p>{html.escape(session_note)}</p></section><h2>Latest executable-depth table</h2><p>Every five-point depth field refers to currently resting orders within $0.05 probability of the corresponding best quote. Shares and price-weighted dollar notional are shown separately. Best bid and best ask are intentionally omitted.</p><div class=\"scroll\"><table><thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for _, label in table_columns)}</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div><h2>Lifecycle events</h2><p>The condition ID identifies the physical Polymarket contract. A related condition ID points either to the prior physical contract for a true replacement, or to a comparison contract in the same threshold family; the event type and details distinguish those cases. Full history remains append-only, while update summaries report only newly detected events.</p><div class=\"scroll\"><table><thead><tr>{''.join(f'<th>{html.escape(field)}</th>' for field in ['Detected At','Event','Market','Event Type','Condition ID','Related Condition ID'])}</tr></thead><tbody>{''.join(lifecycle_rows)}</tbody></table></div></main></body></html>"""
    document = (
        document
        .replace(
            f'<div class="label">Most resilient current 5-point book</div><div class="kpi">${raw_resilient_value:,.0f}</div>',
            f'<div class="label">Most effective liquidity</div><div class="kpi">${resilient_value:,.0f}</div>',
        )
        .replace("Easiest current 5-point move", "Least effective liquidity")
        .replace("Most resilient current 5-point book", "Most effective liquidity")
        .replace("Physical-instance volume", "Current-listing volume")
        .replace("physical-instance traded volume", "current-listing volume")
        .replace("logical-lifetime volume", "continuous-market volume")
        .replace(
            "Use the buttons above the chart to switch between dollars and shares.",
            "Use the buttons above the chart to compare effective dollars, raw five-point dollars, and raw five-point shares. Effective depth gives each order half as much weight for every probability point it sits away from the best quote.",
        )
        .replace(
            "Lower bars are easier to push: the metric is the smaller of ask notional through +5 points and bid notional through −5 points.",
            "Lower bars are easier to push: the metric is the smaller of exponentially distance-weighted bid and ask dollar depth.",
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def run_orderbook_update(data_dir: Path, *, timeout: float = 20, workers: int = 7) -> dict[str, Any]:
    detected_at = utc_timestamp()
    session = build_session()
    raw_markets = fetch_all_markets(session, timeout, workers)
    current = [
        instance_from_market(event_key, event_slug, market, detected_at)
        for event_key, event_slug, market in raw_markets
    ]
    instance_path = data_dir / "market_instances.csv"
    lifecycle_path = data_dir / "market_lifecycle_events.csv"
    depth_path = depth_partition_path(data_dir, detected_at)
    summary_path = data_dir / "logical_market_summary.csv"
    report_path = data_dir / "orderbook_depth_report.html"

    instances, new_events = reconcile_instances(read_csv(instance_path), current, detected_at)
    lifecycle = read_csv(lifecycle_path)
    lifecycle_keys = {
        (row.get("Detected At"), row.get("Event Type"), row.get("Condition ID"))
        for row in lifecycle
    }
    lifecycle.extend(
        row for row in new_events
        if (row["Detected At"], row["Event Type"], row["Condition ID"]) not in lifecycle_keys
    )
    depth_rows = collect_depth_rows(session, instances, detected_at, timeout)
    summaries = build_logical_summary(instances)

    write_csv(instance_path, INSTANCE_FIELDS, instances)
    write_csv(lifecycle_path, LIFECYCLE_FIELDS, lifecycle)
    append_depth(depth_path, depth_rows)
    write_csv(summary_path, SUMMARY_FIELDS, summaries)
    write_report(report_path, read_depth_history(data_dir), lifecycle)
    return {
        "physical_instances": len(instances),
        "present_markets": sum(is_true(row.get("Present")) for row in instances),
        "available_books": sum(row.get("Book Status") == "available" for row in depth_rows),
        "lifecycle_events_added": len(new_events),
        "new_lifecycle_events": [
            {
                "event": row["Event Key"], "market": row["Market Label"],
                "type": row["Event Type"], "condition_id": row["Condition ID"],
                "related_condition_id": row["Related Condition ID"],
            }
            for row in new_events
        ],
        "logical_markets": len(summaries),
    }
