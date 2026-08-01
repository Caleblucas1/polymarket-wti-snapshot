from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from signal_research.live_flow_mon_btc import (
    DEFAULT_CONFIG,
    DEFAULT_RECORD,
    UTC,
    calculate_performance,
    canonical_hash,
    iso_utc,
    load_json,
    mark_schedule,
    parse_utc,
    update_record,
    validate_static,
)


ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/aggTrades"


def archive_url(symbol: str, target: datetime) -> str:
    day = target.strftime("%Y-%m-%d")
    return f"{ARCHIVE_BASE}/{symbol}/{symbol}-aggTrades-{day}.zip"


def _parse_archive_rows(content: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"expected one CSV in Binance archive, found {names}")
        raw = archive.read(names[0]).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    if rows and rows[0] and not rows[0][0].lstrip("-").isdigit():
        rows = rows[1:]
    return rows


def archive_execution_observation(
    session: requests.Session,
    symbol: str,
    target: datetime,
) -> dict[str, Any] | None:
    url = archive_url(symbol, target)
    response = session.get(url, timeout=60)
    if response.status_code in {403, 404}:
        return None
    if response.status_code != 200:
        raise RuntimeError(
            f"Binance public archive request failed: {response.status_code} {url} {response.text[:300]}"
        )
    rows = _parse_archive_rows(response.content)
    target_ms = int(target.timestamp() * 1000)
    eligible: list[list[str]] = []
    for row in rows:
        if len(row) < 7:
            continue
        try:
            event_ms = int(row[5])
        except ValueError:
            continue
        if event_ms >= target_ms:
            eligible.append(row)
    if not eligible:
        raise RuntimeError(f"archive contains no trade at or after {iso_utc(target)}")
    row = min(eligible, key=lambda item: (int(item[5]), int(item[0])))
    event_ms = int(row[5])
    zip_hash = hashlib.sha256(response.content).hexdigest()
    return {
        "target_timestamp_utc": iso_utc(target),
        "observed_at_utc": iso_utc(datetime.fromtimestamp(event_ms / 1000, tz=UTC)),
        "price": float(row[1]),
        "quantity_btc": float(row[2]),
        "source_method": "binance_public_archive_earliest_aggregate_trade",
        "aggregate_trade_id": int(row[0]),
        "buyer_was_maker": str(row[6]).strip().lower() == "true",
        "archive_url": url,
        "archive_zip_sha256": zip_hash,
        "source_payload_hash": canonical_hash(row),
        "publication_lag_note": "Binance publishes finalized daily public-data files the following day; the frozen market timestamp is unchanged.",
    }


def _targets(config: dict[str, Any], as_of: datetime) -> tuple[datetime, list[datetime], datetime]:
    entry = parse_utc(config["entry_timestamp_utc"])
    exit_ = parse_utc(config["exit_timestamp_utc"])
    marks = mark_schedule(entry, exit_, as_of)
    return entry, marks, exit_


def update_from_archive(
    config: dict[str, Any],
    record: dict[str, Any],
    session: requests.Session,
    as_of: datetime,
    api_error: str,
) -> dict[str, Any]:
    entry_time, mark_times, exit_time = _targets(config, as_of)
    symbol = config["instrument"].split()[0]
    pending: list[str] = []

    def eligible_for_archive(target: datetime) -> bool:
        return target.date() < as_of.date()

    if record.get("entry") is None:
        if eligible_for_archive(entry_time):
            record["entry"] = archive_execution_observation(session, symbol, entry_time)
        if record.get("entry") is None:
            pending.append(iso_utc(entry_time))

    existing_marks = {
        row.get("target_timestamp_utc")
        for row in record.get("marks", [])
        if isinstance(row, dict)
    }
    for target in mark_times:
        key = iso_utc(target)
        if key in existing_marks:
            continue
        if eligible_for_archive(target):
            observation = archive_execution_observation(session, symbol, target)
            if observation is not None:
                record.setdefault("marks", []).append(observation)
                continue
        pending.append(key)
    record["marks"] = sorted(record.get("marks", []), key=lambda row: row["target_timestamp_utc"])

    if as_of >= exit_time and record.get("exit") is None:
        if eligible_for_archive(exit_time):
            record["exit"] = archive_execution_observation(session, symbol, exit_time)
        if record.get("exit") is None:
            pending.append(iso_utc(exit_time))

    if record.get("entry") is None:
        status = "awaiting_official_archive"
    elif as_of >= exit_time and record.get("exit") is None:
        status = "awaiting_exit_archive"
    elif record.get("exit") is not None:
        status = "closed"
    else:
        status = "open_archive_lagged"

    record["status"] = status
    record["funding_observations"] = record.get("funding_observations", [])
    record["funding_status"] = "pending_official_monthly_archive"
    record["performance"] = calculate_performance(config, record)
    if isinstance(record.get("performance"), dict):
        record["performance"]["funding_complete"] = False
        record["performance"]["estimated_after_cost_return_if_closed"] = None
        record["performance"]["provisional_gross_minus_execution_cost"] = (
            record["performance"]["gross_return"]
            + record["performance"]["assumed_round_trip_execution_cost_return"]
        )
    record["last_updated_at_utc"] = iso_utc(as_of)
    record["data_quality"] = {
        "source": "Binance official public-data archive",
        "complete": status == "closed" and not pending,
        "live_api_status": "restricted_location_http_451",
        "live_api_error": api_error,
        "archive_publication_lag": True,
        "pending_target_timestamps_utc": sorted(set(pending)),
        "funding_complete": False,
        "errors": [],
    }
    record["real_money_trading_authorized"] = False
    record["record_fingerprint"] = canonical_hash(
        {key: value for key, value in record.items() if key != "record_fingerprint"}
    )
    return record


def collect_resilient(
    config: dict[str, Any],
    record: dict[str, Any],
    session: requests.Session,
    as_of: datetime,
) -> dict[str, Any]:
    try:
        return update_record(config, record, session, as_of)
    except RuntimeError as exc:
        message = str(exc)
        if "451" not in message and "restricted location" not in message.lower():
            raise
        return update_from_archive(config, record, session, as_of, message)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect FLOW-MON-BTC using live API with official archive fallback"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--record", default=str(DEFAULT_RECORD))
    parser.add_argument("--as-of")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config)
    record = load_json(args.record)
    errors = validate_static(config, record)
    if errors:
        raise SystemExit("; ".join(errors))
    as_of = parse_utc(args.as_of) if args.as_of else datetime.now(tz=timezone.utc)

    session = requests.Session()
    session.headers.update({"User-Agent": "signals-research-shadow/1.0"})
    updated = collect_resilient(config, record, session, as_of)
    rendered = json.dumps(updated, indent=2, sort_keys=True) + "\n"
    print(rendered)
    if not args.dry_run:
        Path(args.record).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
