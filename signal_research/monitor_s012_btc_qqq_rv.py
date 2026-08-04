from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from backtest_s012_btc_qqq_rv import (
    DEFAULT_START,
    HORIZONS,
    PROSPECTIVE_BOUNDARY,
    ROUND_TRIP_COST_BPS,
    build_comparable_observations,
    event_outcome,
    extract_trigger_indices,
    iso_z,
    load_data,
    parse_date,
    serialize_event,
)

UTC = timezone.utc


def build_shadow_record(btc_points, qqq_points, *, as_of: date, cost_bps: float) -> dict:
    observations = build_comparable_observations(btc_points, qqq_points)
    trigger_indices = extract_trigger_indices(observations)
    prospective_indices = [
        index
        for index in trigger_indices
        if observations[index].decision_date >= PROSPECTIVE_BOUNDARY
    ]
    events: list[dict] = []
    for index in prospective_indices:
        trigger = observations[index]
        event = {
            "trigger_date": trigger.decision_date.isoformat(),
            "decision_timestamp_utc": iso_z(trigger.decision_at),
            "regime": trigger.regime,
            "btc_realized_volatility": trigger.btc_rv,
            "qqq_realized_volatility": trigger.qqq_rv,
            "volatility_ratio": trigger.ratio,
            "outcomes": {},
        }
        for horizon in (*HORIZONS, "crossover"):
            outcome = event_outcome(
                index, observations, btc_points, horizon, cost_bps=cost_bps
            )
            event["outcomes"][str(horizon)] = (
                {"status": "complete", **serialize_event(outcome)}
                if outcome is not None
                else {"status": "pending"}
            )
        events.append(event)

    latest = observations[-1] if observations else None
    last_trigger = observations[trigger_indices[-1]] if trigger_indices else None
    return {
        "signal_id": "S-012",
        "registry_id": "BTC-QQQ-REALIZED-VOL-COMPRESSION-001",
        "record_type": "untouched_prospective_shadow",
        "as_of_date": as_of.isoformat(),
        "prospective_boundary": PROSPECTIVE_BOUNDARY.isoformat(),
        "cost_assumption_round_trip_bps": cost_bps,
        "status": (
            "active_compression_regime"
            if latest is not None and latest.btc_rv < latest.qqq_rv
            else "armed_or_waiting_for_fresh_crossover"
        ),
        "latest_comparable_observation": (
            {
                "decision_date": latest.decision_date.isoformat(),
                "decision_timestamp_utc": iso_z(latest.decision_at),
                "btc_realized_volatility": latest.btc_rv,
                "qqq_realized_volatility": latest.qqq_rv,
                "volatility_ratio": latest.ratio,
                "btc_below_qqq": latest.btc_rv < latest.qqq_rv,
                "regime": latest.regime,
            }
            if latest is not None
            else None
        ),
        "last_historical_or_prospective_trigger": (
            {
                "decision_date": last_trigger.decision_date.isoformat(),
                "volatility_ratio": last_trigger.ratio,
                "is_prospective": last_trigger.decision_date >= PROSPECTIVE_BOUNDARY,
            }
            if last_trigger is not None
            else None
        ),
        "prospective_events": events,
        "prospective_event_count": len(events),
        "capital_rights": "none",
        "real_money_trading_authorized": False,
        "execution_note": "This record is an observation ledger only. It does not place orders or authorize capital.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update the S-012 untouched prospective shadow record"
    )
    parser.add_argument(
        "--as-of", type=parse_date, default=datetime.now(tz=UTC).date()
    )
    parser.add_argument("--start", type=parse_date, default=DEFAULT_START)
    parser.add_argument("--cost-bps", type=float, default=ROUND_TRIP_COST_BPS)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/s012"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    btc, qqq, sources = load_data(
        args.start, args.as_of, args.cache_dir, args.refresh
    )
    record = build_shadow_record(
        btc, qqq, as_of=args.as_of, cost_bps=args.cost_bps
    )
    record["data_sources"] = sources
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": record["status"],
                "prospective_event_count": record["prospective_event_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
