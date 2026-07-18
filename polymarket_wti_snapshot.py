#!/usr/bin/env python3
"""Export daily Polymarket WTI price-bin probability snapshots to CSV."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_SLUG = "what-price-will-wti-hit-in-july-2026"
DEFAULT_OUTPUT = "wti_july_2026_9am_snapshot.csv"
DEFAULT_RANGE_OUTPUT = "wti_july_2026_9am_ranges.csv"
DEFAULT_CHART_OUTPUT = "wti_7_day_time_series.html"
GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/{slug}"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"
CLOB_BATCH_HISTORY_URL = "https://clob.polymarket.com/batch-prices-history"
BATCH_MARKET_LIMIT = 20


@dataclass(frozen=True)
class TrackerResult:
    """Structured result shared by individual and aggregate tracker commands."""

    status: Literal["appended", "current", "closed", "failed"]
    exit_code: int = 0
    added_dates: int = 0
    row_count: int = 0


def build_session() -> requests.Session:
    """Create an HTTP session that retries transient API failures."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        # POST is included because the batch-history endpoint is read-only and
        # idempotent even though it accepts its query in a JSON body.
        allowed_methods=("GET", "POST"),
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


def market_is_closed(market: dict[str, Any]) -> bool:
    """Return whether Gamma marks a market as closed."""
    value = market.get("closed")
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def all_markets_closed(markets: Iterable[dict[str, Any]]) -> bool:
    """Return true only when an event has markets and every one is closed."""
    market_list = list(markets)
    return bool(market_list) and all(market_is_closed(market) for market in market_list)


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


def missing_snapshot_targets(
    path: Path,
    targets: Iterable[datetime],
    *,
    label_column: str = "Price Bin",
) -> list[datetime]:
    """Return only targets whose date columns are absent from an existing CSV."""
    target_list = list(targets)
    existing_dates = stored_snapshot_dates(path, label_column=label_column)
    return [
        target
        for target in target_list
        if target.date().isoformat() not in existing_dates
    ]


def stored_snapshot_dates(
    path: Path,
    *,
    label_column: str = "Price Bin",
) -> set[str]:
    """Return validated date columns already stored in a snapshot CSV."""
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.reader(input_file)
        header = next(reader, None)
    if not header or label_column not in header:
        raise ValueError(f"Existing CSV must contain a {label_column!r} column")
    existing_dates = {column for column in header if column != label_column}
    for date_string in existing_dates:
        try:
            date.fromisoformat(date_string)
        except ValueError as exc:
            raise ValueError(
                f"Existing CSV has an invalid ISO date column: {date_string}"
            ) from exc
    return existing_dates


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


def probability_range(
    history: Iterable[dict[str, Any]],
    target: datetime,
    *,
    hours: int = 24,
) -> tuple[float | None, float | None]:
    """Return the observed low and high in the window ending at a target."""
    if hours < 1:
        raise ValueError("hours must be at least 1")
    timestamps, prices = normalize_history(history)
    start_timestamp = target.timestamp() - hours * 60 * 60
    start_index = bisect.bisect_left(timestamps, start_timestamp)
    end_index = bisect.bisect_right(timestamps, target.timestamp())
    window = prices[start_index:end_index]
    if not window:
        return None, None
    return min(window), max(window)


def missing_range_targets(
    path: Path,
    targets: Iterable[datetime],
    *,
    label_column: str = "Price Bin",
) -> list[datetime]:
    """Return targets not yet represented in a cumulative range CSV."""
    target_list = list(targets)
    if not path.exists():
        return target_list

    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        required = {label_column, "Date", "Low", "High"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"Existing range CSV must contain {', '.join(sorted(required))}"
            )
        existing_dates = set()
        for row in reader:
            date_string = str(row.get("Date") or "").strip()
            try:
                date.fromisoformat(date_string)
            except ValueError as exc:
                raise ValueError(
                    f"Existing range CSV has an invalid ISO date: {date_string}"
                ) from exc
            existing_dates.add(date_string)
    return [
        target
        for target in target_list
        if target.date().isoformat() not in existing_dates
    ]


def range_output_for_snapshot(path: Path) -> Path:
    """Return the default companion range path for a snapshot CSV."""
    suffix = "_snapshot.csv"
    if path.name.endswith(suffix):
        return path.with_name(f"{path.name[:-len(suffix)]}_ranges.csv")
    return path.with_name(f"{path.stem}_ranges.csv")


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


def fetch_histories(
    session: requests.Session,
    token_ids: list[str],
    targets: list[datetime],
    timeout: float,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch histories in batches, falling back to one request per failed batch."""
    if not token_ids or not targets:
        return {}

    # Preserve the old rolling one-week lookback even when callers request fewer
    # than seven target dates. For a normal seven-day run, one day before the
    # earliest target and seven days before the latest target are identical.
    earliest_target = min(target.timestamp() for target in targets)
    latest_target = max(target.timestamp() for target in targets)
    # Although the API schema describes these values as numeric, the live batch
    # endpoint rejects fractional Unix timestamps. Datetime.timestamp() returns
    # a float, so normalize both bounds to whole seconds before posting.
    start_timestamp = int(
        min(earliest_target - 24 * 60 * 60, latest_target - 7 * 24 * 60 * 60)
    )
    end_timestamp = int(latest_target) + 5 * 60
    histories: dict[str, list[dict[str, Any]]] = {}

    for start in range(0, len(token_ids), BATCH_MARKET_LIMIT):
        chunk = token_ids[start : start + BATCH_MARKET_LIMIT]
        try:
            response = session.post(
                CLOB_BATCH_HISTORY_URL,
                json={
                    "markets": chunk,
                    "start_ts": start_timestamp,
                    "end_ts": end_timestamp,
                    "fidelity": 5,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            history_map = response.json().get("history", {})
            if not isinstance(history_map, dict):
                raise ValueError("CLOB batch API returned an unexpected response")
            for token_id in chunk:
                history = history_map.get(token_id, [])
                histories[token_id] = history if isinstance(history, list) else []
            continue
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            logging.warning("Batch history request failed; using individual requests: %s", exc)

        for token_id in chunk:
            try:
                histories[token_id] = fetch_history(session, token_id, timeout)
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                logging.warning("Skipping token %s: %s", token_id, exc)
                histories[token_id] = []
    return histories


def collect_rows_and_ranges(
    session: requests.Session,
    markets: Iterable[dict[str, Any]],
    targets: list[datetime],
    timeout: float,
    *,
    label_column: str = "Price Bin",
) -> tuple[
    list[dict[str, str | float | None]],
    list[dict[str, str | float | None]],
]:
    """Collect snapshots and trailing-24-hour ranges from one history fetch."""
    market_records: list[tuple[str, str]] = []
    for market in markets:
        label = market.get("groupItemTitle") or market.get("question") or "Unknown market"
        token_id = yes_token_id(market)
        if token_id is None:
            logging.warning("Skipping %s: no CLOB token IDs", label)
            continue
        market_records.append((str(label), token_id))

    histories = fetch_histories(
        session,
        [token_id for _, token_id in market_records],
        targets,
        timeout,
    )
    rows: list[dict[str, str | float | None]] = []
    range_rows: list[dict[str, str | float | None]] = []
    for label, token_id in market_records:
        history = histories.get(token_id, [])
        if not history:
            logging.warning("Skipping %s: no price history", label)
            continue

        row: dict[str, str | float | None] = {label_column: str(label)}
        for target, price in zip(targets, prices_at_or_before(history, targets)):
            row[target.date().isoformat()] = None if price is None else round(price * 100, 1)
            low, high = probability_range(history, target)
            # A resolved or inactive market may have no new observation inside
            # the window even though its last price remains the snapshot value.
            # Represent that carried-forward day as a zero-width range.
            if low is None and high is None and price is not None:
                low = high = price
            range_rows.append(
                {
                    label_column: str(label),
                    "Date": target.date().isoformat(),
                    "Low": None if low is None else round(low * 100, 1),
                    "High": None if high is None else round(high * 100, 1),
                }
            )
        rows.append(row)
    return rows, range_rows


def collect_rows(
    session: requests.Session,
    markets: Iterable[dict[str, Any]],
    targets: list[datetime],
    timeout: float,
    *,
    label_column: str = "Price Bin",
) -> list[dict[str, str | float | None]]:
    """Compatibility wrapper returning only snapshot rows."""
    rows, _ = collect_rows_and_ranges(
        session,
        markets,
        targets,
        timeout,
        label_column=label_column,
    )
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


def merge_and_write_range_csv(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    label_column: str = "Price Bin",
) -> tuple[int, int]:
    """Append new label/date ranges without revising stored range values."""
    fieldnames = [label_column, "Date", "Low", "High"]
    existing_rows: list[dict[str, Any]] = []
    existing_keys: set[tuple[str, str]] = set()
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as input_file:
            reader = csv.DictReader(input_file)
            if not reader.fieldnames or not set(fieldnames).issubset(reader.fieldnames):
                raise ValueError(
                    f"Existing range CSV must contain {', '.join(fieldnames)}"
                )
            for row in reader:
                label = str(row.get(label_column) or "").strip()
                date_string = str(row.get("Date") or "").strip()
                if not label:
                    raise ValueError("Existing range CSV contains a row without a label")
                try:
                    date.fromisoformat(date_string)
                except ValueError as exc:
                    raise ValueError(
                        f"Existing range CSV has an invalid ISO date: {date_string}"
                    ) from exc
                key = (label, date_string)
                if key in existing_keys:
                    raise ValueError(
                        f"Existing range CSV contains a duplicate row: {label} {date_string}"
                    )
                existing_keys.add(key)
                existing_rows.append({field: row.get(field) for field in fieldnames})

    new_rows: list[dict[str, Any]] = []
    for row in rows:
        label = str(row.get(label_column) or "").strip()
        date_string = str(row.get("Date") or "").strip()
        if not label or not date_string:
            continue
        key = (label, date_string)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        new_rows.append({field: row.get(field) for field in fieldnames})

    if not new_rows:
        return 0, len(existing_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined_rows = existing_rows + new_rows
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(combined_rows)
    temporary_path.replace(path)
    return len(new_rows), len(combined_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export daily 9 AM ET Polymarket probability snapshots to CSV."
    )
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Polymarket event slug")
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT), help="CSV output path")
    parser.add_argument(
        "--range-output",
        type=Path,
        default=Path(DEFAULT_RANGE_OUTPUT),
        help="Trailing-24-hour probability range CSV output path",
    )
    parser.add_argument(
        "--chart-output",
        type=Path,
        default=Path(DEFAULT_CHART_OUTPUT),
        help="HTML chart output path",
    )
    parser.add_argument("--days", type=int, default=7, help="Number of calendar-day snapshots")
    parser.add_argument("--hour", type=int, default=9, help="Eastern snapshot hour (0-23)")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    parser.add_argument("--no-chart", action="store_true", help="Update only the CSV")
    return parser.parse_args()


def write_snapshot_chart(args: argparse.Namespace) -> int:
    """Render the stored WTI snapshot without fetching market history."""
    from plot_wti_timeseries import write_chart

    title = str(getattr(args, "title", "What price will WTI hit in July 2026?"))
    return write_chart(
        args.output,
        args.chart_output,
        range_path=getattr(args, "range_output", None),
        days=args.days,
        title_prefix=title,
    )


def run_snapshot(args: argparse.Namespace) -> TrackerResult:
    """Run one append-only price snapshot update."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        requested_targets = snapshot_targets(
            datetime.now(tz=ZoneInfo("UTC")), days=args.days, hour=args.hour
        )
        snapshot_targets_to_add = missing_snapshot_targets(args.output, requested_targets)
        configured_range_output = getattr(args, "range_output", None)
        range_output = (
            Path(configured_range_output)
            if configured_range_output is not None
            else range_output_for_snapshot(args.output)
        )
        range_targets_to_add = missing_range_targets(range_output, requested_targets)
        targets_by_date = {
            target.date().isoformat(): target
            for target in snapshot_targets_to_add + range_targets_to_add
        }
        targets = [targets_by_date[key] for key in sorted(targets_by_date)]
    except ValueError as exc:
        logging.error("Invalid arguments: %s", exc)
        return TrackerResult("failed", exit_code=2)
    if not targets:
        logging.info("All requested snapshot dates already exist; no API calls were needed")
        if not args.no_chart:
            try:
                series_count = write_snapshot_chart(args)
            except (OSError, ValueError) as exc:
                logging.error("Could not create chart: %s", exc)
                return TrackerResult("failed", exit_code=1)
            logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
        return TrackerResult("current")

    session = build_session()
    try:
        event = fetch_event(session, args.slug, args.timeout)
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        logging.error("Could not fetch event: %s", exc)
        return TrackerResult("failed", exit_code=1)

    markets = event.get("markets", [])
    if not isinstance(markets, list) or not markets:
        logging.error("The event contains no markets")
        return TrackerResult("failed", exit_code=1)
    if all_markets_closed(markets):
        logging.info("All event markets are closed; no snapshot date was appended")
        if not args.no_chart and args.output.exists():
            try:
                series_count = write_snapshot_chart(args)
            except (OSError, ValueError) as exc:
                logging.error("Could not create chart: %s", exc)
                return TrackerResult("failed", exit_code=1)
            logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
        return TrackerResult("closed")

    logging.info("Fetching %d price bins", len(markets))
    rows, range_rows = collect_rows_and_ranges(session, markets, targets, args.timeout)
    try:
        added_dates, total_rows = merge_and_write_csv(
            args.output,
            rows,
            snapshot_targets_to_add,
        )
        added_ranges, total_ranges = merge_and_write_range_csv(
            range_output,
            range_rows,
        )
    except (OSError, ValueError) as exc:
        logging.error("Could not update CSV: %s", exc)
        return TrackerResult("failed", exit_code=1)
    if not args.no_chart:
        try:
            series_count = write_snapshot_chart(args)
        except (OSError, ValueError) as exc:
            logging.error("Could not create chart: %s", exc)
            return TrackerResult("failed", exit_code=1)
        logging.info("Created chart with %d price bins at %s", series_count, args.chart_output)
    logging.info(
        "Added %d new date(s); CSV contains %d rows at %s; "
        "stored %d new range row(s) (%d total) at %s",
        added_dates,
        total_rows,
        args.output,
        added_ranges,
        total_ranges,
        range_output,
    )
    status = "appended" if added_dates else "current"
    return TrackerResult(status, added_dates=added_dates, row_count=total_rows)


def main() -> int:
    return run_snapshot(parse_args()).exit_code


if __name__ == "__main__":
    raise SystemExit(main())
