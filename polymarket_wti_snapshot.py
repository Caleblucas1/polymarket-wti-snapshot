#!/usr/bin/env python3
"""Export daily Polymarket WTI price-bin probability snapshots to CSV."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_SLUG = "what-price-will-wti-hit-in-july-2026"
DEFAULT_OUTPUT = "wti_july_2026_9am_snapshot.csv"
GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"


def build_session() -> requests.Session:
    """Create an HTTP session that retries transient API failures."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": "polymarket-wti-snapshot/1.0"})
    return session


def parse_json_array(value: Any) -> list[Any]:
    """Accept Gamma API array fields returned as arrays or JSON strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def yes_token_id(market: dict[str, Any]) -> str | None:
    """Return the token corresponding to the Yes outcome."""
    token_ids = parse_json_array(market.get("clobTokenIds"))
    outcomes = parse_json_array(market.get("outcomes"))
    if not token_ids:
        return None

    for index, outcome in enumerate(outcomes):
        if str(outcome).strip().lower() == "yes" and index < len(token_ids):
            return str(token_ids[index])
    return str(token_ids[0])


def snapshot_targets(
    now: datetime,
    *,
    days: int = 7,
    hour: int = 9,
    timezone: str = "America/New_York",
) -> list[datetime]:
    """Return the most recent past daily wall-clock snapshot times."""
    if days < 1:
        raise ValueError("days must be at least 1")
    if not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23")

    tz = ZoneInfo(timezone)
    local_now = now.astimezone(tz)
    latest_date = local_now.date()
    latest_target = datetime.combine(latest_date, time(hour), tzinfo=tz)
    if local_now < latest_target:
        latest_date -= timedelta(days=1)

    dates = [latest_date - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    return [datetime.combine(day, time(hour), tzinfo=tz) for day in dates]


def normalize_history(history: Iterable[dict[str, Any]]) -> tuple[list[float], list[float]]:
    """Return valid history timestamps and prices, sorted by timestamp."""
    points: list[tuple[float, float]] = []
    for item in history:
        try:
            timestamp = float(item["t"])
            price = float(item["p"])
        except (KeyError, TypeError, ValueError):
            continue
        points.append((timestamp, price))
    points.sort(key=lambda point: point[0])
    return [point[0] for point in points], [point[1] for point in points]


def prices_at_or_before(
    history: Iterable[dict[str, Any]], targets: Iterable[datetime]
) -> list[float | None]:
    """Find the latest observed price at or before each target."""
    timestamps, prices = normalize_history(history)
    results: list[float | None] = []
    for target in targets:
        index = bisect.bisect_right(timestamps, target.timestamp()) - 1
        results.append(prices[index] if index >= 0 else None)
    return results


def fetch_event(session: requests.Session, slug: str, timeout: float) -> dict[str, Any]:
    response = session.get(GAMMA_EVENT_URL.format(slug=slug), timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Gamma API returned an unexpected event response")
    return payload


def fetch_history(
    session: requests.Session, token_id: str, timeout: float
) -> list[dict[str, Any]]:
    response = session.get(
        CLOB_HISTORY_URL,
        # The CLOB API currently requires at least five-minute fidelity for a
        # one-week range.
        params={"market": token_id, "interval": "1w", "fidelity": 5},
        timeout=timeout,
    )
    response.raise_for_status()
    history = response.json().get("history", [])
    if not isinstance(history, list):
        raise ValueError("CLOB API returned an unexpected history response")
    return history


def collect_rows(
    session: requests.Session,
    markets: Iterable[dict[str, Any]],
    targets: list[datetime],
    timeout: float,
    *,
    label_column: str = "Price Bin",
) -> list[dict[str, str | float | None]]:
    rows: list[dict[str, str | float | None]] = []
    for market in markets:
        label = market.get("groupItemTitle") or market.get("question") or "Unknown market"
        token_id = yes_token_id(market)
        if token_id is None:
            logging.warning("Skipping %s: no CLOB token IDs", label)
            continue

        try:
            history = fetch_history(session, token_id, timeout)
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            logging.warning("Skipping %s: %s", label, exc)
            continue
        if not history:
            logging.warning("Skipping %s: no price history", label)
            continue

        row: dict[str, str | float | None] = {label_column: str(label)}
        for target, price in zip(targets, prices_at_or_before(history, targets)):
            row[target.date().isoformat()] = None if price is None else round(price * 100, 1)
        rows.append(row)
    return rows


def merge_and_write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    targets: list[datetime],
    *,
    label_column: str = "Price Bin",
) -> tuple[int, int]:
    """Append missing date columns while preserving previously saved snapshots."""
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming_dates = [target.date().isoformat() for target in targets]
    existing_dates: list[str] = []
    existing_rows: list[dict[str, Any]] = []

    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as input_file:
            reader = csv.DictReader(input_file)
            if not reader.fieldnames or label_column not in reader.fieldnames:
                raise ValueError(
                    f"Existing CSV must contain a {label_column!r} column"
                )
            existing_dates = [
                column for column in reader.fieldnames if column != label_column
            ]
            for date_string in existing_dates:
                try:
                    date.fromisoformat(date_string)
                except ValueError as exc:
                    raise ValueError(
                        f"Existing CSV has an invalid ISO date column: {date_string}"
                    ) from exc
            existing_rows = list(reader)

    new_dates = [date_string for date_string in incoming_dates if date_string not in existing_dates]
    if path.exists() and not new_dates:
        return 0, len(existing_rows)

    combined_dates = sorted(set(existing_dates + new_dates))
    rows_by_label: dict[str, dict[str, Any]] = {}
    label_order: list[str] = []
    for row in existing_rows:
        label = str(row.get(label_column) or "").strip()
        if not label:
            raise ValueError("Existing CSV contains a row without a price-bin label")
        if label in rows_by_label:
            raise ValueError(f"Existing CSV contains duplicate price bin: {label}")
        rows_by_label[label] = {label_column: label, **row}
        label_order.append(label)

    for incoming_row in rows:
        label = str(incoming_row[label_column])
        if label not in rows_by_label:
            rows_by_label[label] = {label_column: label}
            label_order.append(label)
        for date_string in new_dates:
            rows_by_label[label][date_string] = incoming_row.get(date_string)

    fieldnames = [label_column, *combined_dates]
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_by_label[label] for label in label_order)
    temporary_path.replace(path)
    return len(new_dates), len(label_order)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export daily 9 AM ET Polymarket probability snapshots to CSV."
    )
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Polymarket event slug")
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT), help="CSV output path")
    parser.add_argument("--days", type=int, default=7, help="Number of calendar-day snapshots")
    parser.add_argument("--hour", type=int, default=9, help="Eastern snapshot hour (0-23)")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        targets = snapshot_targets(
            datetime.now(tz=ZoneInfo("UTC")), days=args.days, hour=args.hour
        )
    except ValueError as exc:
        logging.error("Invalid arguments: %s", exc)
        return 2

    session = build_session()
    try:
        event = fetch_event(session, args.slug, args.timeout)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        logging.error("Could not fetch event: %s", exc)
        return 1

    markets = event.get("markets", [])
    if not isinstance(markets, list) or not markets:
        logging.error("The event contains no markets")
        return 1

    logging.info("Fetching %d price bins", len(markets))
    rows = collect_rows(session, markets, targets, args.timeout)
    try:
        added_dates, total_rows = merge_and_write_csv(args.output, rows, targets)
    except (OSError, ValueError) as exc:
        logging.error("Could not update CSV: %s", exc)
        return 1
    logging.info(
        "Added %d new date(s); CSV contains %d rows at %s",
        added_dates,
        total_rows,
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
