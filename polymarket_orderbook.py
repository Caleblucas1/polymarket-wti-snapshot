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
from typing import Any, Iterable

import requests

from polymarket_wti_snapshot import build_session, fetch_event, parse_json_array
from track_market import load_registry


CLOB_BOOKS_URL = "https://clob.polymarket.com/books"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"
BOOK_BATCH_LIMIT = 20
DEPTH_BANDS = (0.01, 0.05, 0.10)

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
    "Snapshot At", "Book Timestamp", "Event Key", "Event Slug",
    "Logical Market ID", "Threshold Family ID", "Market Label", "Condition ID",
    "Token ID", "Outcome", "Book Status", "Best Bid", "Best Ask", "Midpoint",
    "Spread", "Bid Levels", "Ask Levels", "Bid Shares Total", "Ask Shares Total",
    "Bid Notional Total", "Ask Notional Total", "Bid Shares 1c", "Ask Shares 1c",
    "Bid Notional 1c", "Ask Notional 1c", "Bid Shares 5c", "Ask Shares 5c",
    "Bid Notional 5c", "Ask Notional 5c", "Bid Shares 10c", "Ask Shares 10c",
    "Bid Notional 10c", "Ask Notional 10c", "Book Hash", "Instance Volume",
    "Logical Lifetime Volume", "Liquidity", "Last Trade Price",
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
        writer = csv.DictWriter(output_file, fieldnames=fields, extrasaction="ignore")
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
    keys = {
        (row.get("Snapshot At", ""), row.get("Condition ID", ""), row.get("Token ID", ""))
        for row in existing
    }
    new_rows = [
        row for row in rows
        if (row["Snapshot At"], row["Condition ID"], row["Token ID"]) not in keys
    ]
    write_csv(path, DEPTH_FIELDS, [*existing, *new_rows])


def write_report(path: Path, rows: list[dict[str, str]], lifecycle: list[dict[str, str]]) -> None:
    import plotly.graph_objects as go

    available = [row for row in rows if row.get("Book Status") == "available"]
    events = sorted({row["Event Key"] for row in available})
    figure = go.Figure()
    for event_key in events:
        event_rows = sorted(
            (row for row in available if row["Event Key"] == event_key),
            key=lambda row: row["Market Label"],
        )
        labels = [row["Market Label"] for row in event_rows]
        custom = [[
            row.get("Best Bid", ""), row.get("Best Ask", ""), row.get("Spread", ""),
            row.get("Bid Shares 5c", ""), row.get("Ask Shares 5c", ""),
            row.get("Instance Volume", ""), row.get("Logical Lifetime Volume", ""),
            row.get("Condition ID", ""),
        ] for row in event_rows]
        figure.add_trace(go.Bar(
            name=f"{event_key} bids", y=labels,
            x=[-float(row.get("Bid Shares 5c") or 0) for row in event_rows],
            orientation="h", marker_color="#2563EB", customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>Bid depth within 5¢: %{customdata[3]:,.0f} shares"
                "<br>Best bid: %{customdata[0]}<br>Best ask: %{customdata[1]}"
                "<br>Spread: %{customdata[2]}<br>Instance volume: %{customdata[5]}"
                "<br>Logical lifetime volume: %{customdata[6]}"
                "<br>Condition: %{customdata[7]}<extra></extra>"
            ),
        ))
        figure.add_trace(go.Bar(
            name=f"{event_key} asks", y=labels,
            x=[float(row.get("Ask Shares 5c") or 0) for row in event_rows],
            orientation="h", marker_color="#DC2626", customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>Ask depth within 5¢: %{customdata[4]:,.0f} shares"
                "<br>Best bid: %{customdata[0]}<br>Best ask: %{customdata[1]}"
                "<br>Spread: %{customdata[2]}<br>Instance volume: %{customdata[5]}"
                "<br>Logical lifetime volume: %{customdata[6]}"
                "<br>Condition: %{customdata[7]}<extra></extra>"
            ),
        ))

    buttons = [{"label": "All events", "method": "update", "args": [{"visible": [True] * len(figure.data)}]}]
    for event_index, event_key in enumerate(events):
        visibility = [False] * len(figure.data)
        visibility[event_index * 2] = True
        visibility[event_index * 2 + 1] = True
        buttons.append({"label": event_key, "method": "update", "args": [{"visible": visibility}]})
    figure.update_layout(
        title={"text": "Polymarket order-book depth by logical market", "x": 0.5},
        template="plotly_white", barmode="relative", height=max(700, 30 * len(available)),
        xaxis_title="Shares within 5¢ of best quote (bids left, asks right)",
        yaxis_title="Market", legend={"orientation": "h"},
        updatemenus=[{"buttons": buttons, "direction": "down", "x": 0, "y": 1.12}],
        margin={"l": 170, "r": 40, "t": 120, "b": 80},
    )
    figure.add_annotation(
        text="Depth is measured on the Yes-token book. Closed or unavailable books remain listed below.",
        xref="paper", yref="paper", x=0, y=-0.08, showarrow=False, xanchor="left",
    )
    plot = figure.to_html(include_plotlyjs="cdn", full_html=False, config={"displaylogo": False, "responsive": True})
    table_rows = []
    for row in sorted(rows, key=lambda value: (value["Event Key"], value["Market Label"])):
        table_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(row.get(field, '')))}</td>"
            for field in ["Event Key", "Market Label", "Book Status", "Best Bid", "Best Ask", "Spread", "Bid Shares 5c", "Ask Shares 5c", "Instance Volume", "Logical Lifetime Volume"]
        ) + "</tr>")
    lifecycle_rows = []
    for row in lifecycle[-100:]:
        lifecycle_rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(row.get(field, '')))}</td>"
            for field in ["Detected At", "Event Key", "Market Label", "Event Type", "Condition ID", "Related Condition ID"]
        ) + "</tr>")
    document = f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Polymarket order-book depth</title><style>body{{font-family:Arial,sans-serif;margin:24px;color:#111827}}table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:16px}}th,td{{border:1px solid #d1d5db;padding:6px;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}th{{background:#f3f4f6;position:sticky;top:0}}.scroll{{overflow:auto;max-height:720px}}p{{color:#4b5563}}</style></head><body>{plot}<h2>Latest depth for every present market</h2><p>Prices are probabilities from 0 to 1; depth columns are Yes shares within five cents of the best quote.</p><div class=\"scroll\"><table><thead><tr>{''.join(f'<th>{html.escape(field)}</th>' for field in ['Event','Market','Status','Best Bid','Best Ask','Spread','Bid 5c','Ask 5c','Instance Volume','Logical Lifetime Volume'])}</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div><h2>Lifecycle events</h2><div class=\"scroll\"><table><thead><tr>{''.join(f'<th>{html.escape(field)}</th>' for field in ['Detected At','Event','Market','Event Type','Condition ID','Related Condition ID'])}</tr></thead><tbody>{''.join(lifecycle_rows)}</tbody></table></div></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")


def run_orderbook_update(data_dir: Path, *, timeout: float = 20, workers: int = 7) -> dict[str, int]:
    detected_at = utc_timestamp()
    session = build_session()
    raw_markets = fetch_all_markets(session, timeout, workers)
    current = [
        instance_from_market(event_key, event_slug, market, detected_at)
        for event_key, event_slug, market in raw_markets
    ]
    instance_path = data_dir / "market_instances.csv"
    lifecycle_path = data_dir / "market_lifecycle_events.csv"
    depth_path = data_dir / "orderbook_depth_snapshots.csv"
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
    write_report(report_path, depth_rows, lifecycle)
    return {
        "physical_instances": len(instances),
        "present_markets": sum(is_true(row.get("Present")) for row in instances),
        "available_books": sum(row.get("Book Status") == "available" for row in depth_rows),
        "lifecycle_events_added": len(new_events),
        "logical_markets": len(summaries),
    }
