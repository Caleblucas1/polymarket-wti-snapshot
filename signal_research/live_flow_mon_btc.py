from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_CONFIG = Path("signal_research/live_tests/FLOW-MON-BTC-2026-08.json")
DEFAULT_RECORD = Path("signal_records/live/FLOW-MON-BTC-2026-08.json")
UTC = timezone.utc


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def fetch_json(
    session: requests.Session,
    base_url: str,
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    response = session.get(f"{base_url}{endpoint}", params=params, timeout=30)
    if response.status_code != 200:
        text = response.text[:500]
        raise RuntimeError(
            f"Binance public API request failed: {response.status_code} {endpoint} {text}"
        )
    return response.json()


def validate_symbol(session: requests.Session, config: dict[str, Any]) -> dict[str, Any]:
    sources = config["data_sources"]
    payload = fetch_json(
        session,
        sources["base_url"],
        sources["exchange_info_endpoint"],
        {},
    )
    symbol = config["instrument"].split()[0]
    matching = [row for row in payload.get("symbols", []) if row.get("symbol") == symbol]
    if len(matching) != 1:
        raise RuntimeError(f"could not uniquely resolve {symbol} in exchangeInfo")
    row = matching[0]
    if row.get("contractType") != "PERPETUAL" or row.get("status") != "TRADING":
        raise RuntimeError(f"{symbol} is not a trading perpetual contract: {row}")
    return {
        "symbol": row["symbol"],
        "contract_type": row["contractType"],
        "status": row["status"],
        "quote_asset": row.get("quoteAsset"),
        "margin_asset": row.get("marginAsset"),
    }


def execution_observation(
    session: requests.Session,
    config: dict[str, Any],
    timestamp: datetime,
) -> dict[str, Any]:
    sources = config["data_sources"]
    symbol = config["instrument"].split()[0]
    window_seconds = int(config["execution_proxy"]["search_window_seconds"])
    start_ms = milliseconds(timestamp)
    end_ms = milliseconds(timestamp + timedelta(seconds=window_seconds)) - 1

    trades = fetch_json(
        session,
        sources["base_url"],
        sources["aggregate_trades_endpoint"],
        {
            "symbol": symbol,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        },
    )
    eligible = [
        trade
        for trade in trades
        if isinstance(trade, dict) and int(trade.get("T", -1)) >= start_ms
    ]
    if eligible:
        trade = min(eligible, key=lambda item: (int(item["T"]), int(item["a"])))
        return {
            "target_timestamp_utc": iso_utc(timestamp),
            "observed_at_utc": iso_utc(datetime.fromtimestamp(int(trade["T"]) / 1000, tz=UTC)),
            "price": float(trade["p"]),
            "quantity_btc": float(trade["q"]),
            "source_method": "earliest_public_aggregate_trade_at_or_after_timestamp",
            "aggregate_trade_id": int(trade["a"]),
            "buyer_was_maker": bool(trade["m"]),
            "source_payload_hash": canonical_hash(trade),
        }

    klines = fetch_json(
        session,
        sources["base_url"],
        sources["klines_endpoint"],
        {
            "symbol": symbol,
            "interval": "1m",
            "startTime": start_ms,
            "endTime": start_ms + 60_000 - 1,
            "limit": 1,
        },
    )
    if not klines:
        raise RuntimeError(f"no aggregate trade or one-minute kline found for {iso_utc(timestamp)}")
    kline = klines[0]
    return {
        "target_timestamp_utc": iso_utc(timestamp),
        "observed_at_utc": iso_utc(datetime.fromtimestamp(int(kline[0]) / 1000, tz=UTC)),
        "price": float(kline[1]),
        "quantity_btc": None,
        "source_method": "one_minute_kline_open_at_timestamp",
        "aggregate_trade_id": None,
        "buyer_was_maker": None,
        "source_payload_hash": canonical_hash(kline),
    }


def funding_observations(
    session: requests.Session,
    config: dict[str, Any],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    sources = config["data_sources"]
    symbol = config["instrument"].split()[0]
    payload = fetch_json(
        session,
        sources["base_url"],
        sources["funding_rate_endpoint"],
        {
            "symbol": symbol,
            "startTime": milliseconds(start),
            "endTime": milliseconds(end),
            "limit": 1000,
        },
    )
    observations: list[dict[str, Any]] = []
    for row in payload:
        funding_time = datetime.fromtimestamp(int(row["fundingTime"]) / 1000, tz=UTC)
        if funding_time < start or funding_time > end:
            continue
        rate = float(row["fundingRate"])
        mark_price = float(row["markPrice"])
        cash_for_one_btc = mark_price * rate
        observations.append(
            {
                "funding_timestamp_utc": iso_utc(funding_time),
                "funding_rate": rate,
                "mark_price": mark_price,
                "long_position_cash_flow_usdt": -cash_for_one_btc,
                "source_payload_hash": canonical_hash(row),
            }
        )
    observations.sort(key=lambda row: row["funding_timestamp_utc"])
    return observations


def mark_schedule(entry: datetime, exit_: datetime, as_of: datetime) -> list[datetime]:
    values: list[datetime] = []
    cursor = entry + timedelta(days=1)
    ceiling = min(exit_, as_of)
    while cursor < exit_ and cursor <= ceiling:
        values.append(cursor)
        cursor += timedelta(days=1)
    return values


def calculate_performance(
    config: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any] | None:
    entry = record.get("entry")
    if not isinstance(entry, dict):
        return None
    current = record.get("exit")
    if not isinstance(current, dict):
        marks = record.get("marks", [])
        current = marks[-1] if marks else entry
    entry_price = float(entry["price"])
    current_price = float(current["price"])
    gross_return = current_price / entry_price - 1.0
    funding_cash = sum(
        float(row["long_position_cash_flow_usdt"])
        for row in record.get("funding_observations", [])
    )
    funding_return = funding_cash / entry_price
    round_trip_cost = float(config["cost_model"]["round_trip_execution_cost_bps"]) / 10_000
    net_if_closed = gross_return + funding_return - round_trip_cost
    return {
        "as_of_timestamp_utc": current["target_timestamp_utc"],
        "entry_price": entry_price,
        "current_or_exit_price": current_price,
        "gross_return": gross_return,
        "cumulative_funding_cash_flow_usdt_for_one_btc": funding_cash,
        "cumulative_funding_return": funding_return,
        "assumed_round_trip_execution_cost_return": -round_trip_cost,
        "estimated_after_cost_return_if_closed": net_if_closed,
        "closed": isinstance(record.get("exit"), dict),
        "notional_note": "Returns are normalized to a one-BTC, one-times-leverage shadow position; no real position exists.",
    }


def update_record(
    config: dict[str, Any],
    record: dict[str, Any],
    session: requests.Session,
    as_of: datetime,
) -> dict[str, Any]:
    entry_time = parse_utc(config["entry_timestamp_utc"])
    exit_time = parse_utc(config["exit_timestamp_utc"])
    if as_of < entry_time:
        record["status"] = "armed"
        return record

    symbol_state = validate_symbol(session, config)
    if record.get("entry") is None:
        record["entry"] = execution_observation(session, config, entry_time)

    existing_mark_times = {
        row.get("target_timestamp_utc")
        for row in record.get("marks", [])
        if isinstance(row, dict)
    }
    for target in mark_schedule(entry_time, exit_time, as_of):
        key = iso_utc(target)
        if key not in existing_mark_times:
            record.setdefault("marks", []).append(execution_observation(session, config, target))
    record["marks"] = sorted(record.get("marks", []), key=lambda row: row["target_timestamp_utc"])

    observation_end = min(as_of, exit_time)
    record["funding_observations"] = funding_observations(
        session,
        config,
        entry_time,
        observation_end,
    )

    if as_of >= exit_time and record.get("exit") is None:
        record["exit"] = execution_observation(session, config, exit_time)
        record["status"] = "closed"
    else:
        record["status"] = "open"

    record["performance"] = calculate_performance(config, record)
    record["last_updated_at_utc"] = iso_utc(as_of)
    record["data_quality"] = {
        "source": "Binance USD-M Futures public REST API",
        "complete": record["entry"] is not None and (
            as_of < exit_time or record.get("exit") is not None
        ),
        "symbol_validation": symbol_state,
        "errors": [],
    }
    record["real_money_trading_authorized"] = False
    record["record_fingerprint"] = canonical_hash(
        {key: value for key, value in record.items() if key != "record_fingerprint"}
    )
    return record


def validate_static(config: dict[str, Any], record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("registry_id") != "FLOW-MON-BTC-001":
        errors.append("config registry_id must be FLOW-MON-BTC-001")
    if config.get("real_money_trading_authorized") is not False:
        errors.append("config must prohibit real-money trading")
    if config.get("test_type") != "untouched_out_of_sample_shadow":
        errors.append("test_type must be untouched_out_of_sample_shadow")
    if parse_utc(config["entry_timestamp_utc"]) != datetime(2026, 8, 1, 0, 5, tzinfo=UTC):
        errors.append("entry timestamp must remain frozen at 2026-08-01T00:05:00Z")
    if parse_utc(config["exit_timestamp_utc"]) != datetime(2026, 8, 8, 0, 5, tzinfo=UTC):
        errors.append("exit timestamp must remain frozen at 2026-08-08T00:05:00Z")
    if record.get("live_test_id") != config.get("live_test_id"):
        errors.append("record live_test_id must match config")
    if record.get("registry_id") != config.get("registry_id"):
        errors.append("record registry_id must match config")
    if record.get("real_money_trading_authorized") is not False:
        errors.append("record must prohibit real-money trading")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect the August 2026 FLOW-MON-BTC live shadow test")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--record", default=str(DEFAULT_RECORD))
    parser.add_argument("--as-of", help="UTC ISO timestamp; defaults to current time")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config)
    record = load_json(args.record)
    static_errors = validate_static(config, record)
    if static_errors:
        raise SystemExit("; ".join(static_errors))

    as_of = parse_utc(args.as_of) if args.as_of else datetime.now(tz=UTC)
    base_override = os.environ.get("BINANCE_FUTURES_BASE_URL")
    if base_override:
        config = json.loads(json.dumps(config))
        config["data_sources"]["base_url"] = base_override.rstrip("/")

    session = requests.Session()
    session.headers.update({"User-Agent": "signals-research-shadow/1.0"})
    updated = update_record(config, record, session, as_of)
    rendered = json.dumps(updated, indent=2, sort_keys=True) + "\n"
    print(rendered)
    if not args.dry_run:
        Path(args.record).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
