from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Sequence

try:
    from .backtest_s012_btc_qqq_rv import (
        DEFAULT_START,
        EventOutcome,
        HORIZONS,
        ROUND_TRIP_COST_BPS,
        benchmark_outcomes,
        build_comparable_observations,
        event_outcome,
        extract_trigger_indices,
        load_data,
        parse_date,
        percentile,
    )
except ImportError:  # Supports direct script execution.
    from backtest_s012_btc_qqq_rv import (
        DEFAULT_START,
        EventOutcome,
        HORIZONS,
        ROUND_TRIP_COST_BPS,
        benchmark_outcomes,
        build_comparable_observations,
        event_outcome,
        extract_trigger_indices,
        load_data,
        parse_date,
        percentile,
    )

SIMULATIONS = 20_000
SEED = 12012026
PRIMARY_HORIZON = 90
PROSPECTIVE_BOUNDARY = date(2026, 8, 4)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonoverlapping_events(rows: Sequence[EventOutcome]) -> list[EventOutcome]:
    """Greedily retain the earliest event after the prior event's exit.

    The canonical trigger ledger preserves every fresh crossover. Inference must not
    pretend that positions whose holding windows overlap are independent samples.
    """
    selected: list[EventOutcome] = []
    last_exit: date | None = None
    for row in sorted(rows, key=lambda item: (item.entry_date, item.trigger_date)):
        if last_exit is None or row.entry_date > last_exit:
            selected.append(row)
            last_exit = row.exit_date
    return selected


def _matched_pool_key(row: EventOutcome) -> tuple[int, str]:
    return row.trigger_date.year, row.split


def matched_null_distribution(
    signal_rows: Sequence[EventOutcome],
    unconditional_rows: Sequence[EventOutcome],
    *,
    simulations: int = SIMULATIONS,
    seed: int = SEED,
) -> list[float]:
    if not signal_rows:
        return []
    pools: dict[tuple[int, str], list[float]] = {}
    for row in unconditional_rows:
        pools.setdefault(_matched_pool_key(row), []).append(row.net_return)
    missing = sorted({_matched_pool_key(row) for row in signal_rows} - set(pools))
    if missing:
        raise ValueError(f"missing matched benchmark pools: {missing}")
    rng = random.Random(seed)
    distribution: list[float] = []
    for _ in range(simulations):
        sampled = [rng.choice(pools[_matched_pool_key(row)]) for row in signal_rows]
        distribution.append(statistics.fmean(sampled))
    return distribution


def observed_summary(rows: Sequence[EventOutcome]) -> dict:
    if not rows:
        return {"event_count": 0}
    values = [row.net_return for row in rows]
    return {
        "event_count": len(rows),
        "mean_net_return": statistics.fmean(values),
        "median_net_return": statistics.median(values),
        "hit_rate_net_positive": sum(value > 0 for value in values) / len(values),
        "worst_max_adverse_excursion": min(row.max_adverse_excursion for row in rows),
        "worst_path_max_drawdown": min(row.max_drawdown for row in rows),
        "trigger_dates": [row.trigger_date.isoformat() for row in rows],
    }


def benchmark_audit(
    signal_rows: Sequence[EventOutcome],
    unconditional_rows: Sequence[EventOutcome],
    *,
    simulations: int = SIMULATIONS,
    seed: int = SEED,
) -> dict:
    observed = observed_summary(signal_rows)
    if not signal_rows:
        return {"observed": observed, "matched_null": None}
    null = matched_null_distribution(
        signal_rows, unconditional_rows, simulations=simulations, seed=seed
    )
    observed_mean = float(observed["mean_net_return"])
    expected = statistics.fmean(null)
    edge = observed_mean - expected
    relative = edge / abs(expected) if abs(expected) > 1e-12 else None
    return {
        "observed": observed,
        "matched_null": {
            "method": "For each signal event, draw one unconditional eligible entry from the same calendar year and source-exposure split; average across events; repeat deterministically.",
            "simulations": simulations,
            "seed": seed,
            "expected_mean_net_return": expected,
            "95pct_interval_of_matched_mean": [
                percentile(null, 0.025),
                percentile(null, 0.975),
            ],
            "observed_percentile": sum(value <= observed_mean for value in null) / len(null),
            "one_sided_probability_null_at_least_observed": sum(
                value >= observed_mean for value in null
            )
            / len(null),
            "absolute_mean_net_edge": edge,
            "relative_improvement_vs_abs_expected_mean": relative,
            "clears_25pct_improvement_target": relative is not None and relative >= 0.25,
        },
    }


def serialize_rows(rows: Sequence[EventOutcome]) -> list[dict]:
    payload: list[dict] = []
    for row in rows:
        value = asdict(row)
        for key in ("trigger_date", "entry_date", "exit_date"):
            value[key] = value[key].isoformat()
        payload.append(value)
    return payload


def audit(
    btc_points,
    qqq_points,
    *,
    cost_bps: float,
    historical_input: Path | None = None,
    simulations: int = SIMULATIONS,
) -> dict:
    observations = build_comparable_observations(btc_points, qqq_points)
    trigger_indices = extract_trigger_indices(observations)
    horizons: dict[str, dict] = {}
    for horizon in HORIZONS:
        events = [
            outcome
            for index in trigger_indices
            if (
                outcome := event_outcome(
                    index, observations, btc_points, horizon, cost_bps=cost_bps
                )
            )
            is not None
        ]
        unconditional = benchmark_outcomes(
            observations, btc_points, horizon, cost_bps=cost_bps
        )
        validation = [
            row for row in events if row.split == "historical_validation_source_exposed"
        ]
        nonoverlap = nonoverlapping_events(events)
        validation_nonoverlap = nonoverlapping_events(validation)
        horizons[str(horizon)] = {
            "canonical_all_fresh_crossovers_descriptive": benchmark_audit(
                events, unconditional, simulations=simulations, seed=SEED + horizon
            ),
            "nonoverlapping_events_primary_inference": benchmark_audit(
                nonoverlap,
                unconditional,
                simulations=simulations,
                seed=SEED + horizon + 1,
            ),
            "source_exposed_validation_descriptive": benchmark_audit(
                validation,
                unconditional,
                simulations=simulations,
                seed=SEED + horizon + 2,
            ),
            "source_exposed_validation_nonoverlapping": benchmark_audit(
                validation_nonoverlap,
                unconditional,
                simulations=simulations,
                seed=SEED + horizon + 3,
            ),
            "nonoverlapping_event_rows": serialize_rows(nonoverlap),
            "validation_nonoverlapping_event_rows": serialize_rows(
                validation_nonoverlap
            ),
        }

    primary = horizons[str(PRIMARY_HORIZON)]
    all_primary = primary["nonoverlapping_events_primary_inference"]
    validation_primary = primary["source_exposed_validation_nonoverlapping"]
    all_null = all_primary["matched_null"] or {}
    validation_null = validation_primary["matched_null"] or {}
    all_count = all_primary["observed"]["event_count"]
    validation_count = validation_primary["observed"]["event_count"]
    all_positive = all_primary["observed"].get("mean_net_return", -math.inf) > 0
    validation_positive = (
        validation_primary["observed"].get("mean_net_return", -math.inf) > 0
    )
    clears_target = bool(all_null.get("clears_25pct_improvement_target"))
    validation_clears = bool(validation_null.get("clears_25pct_improvement_target"))
    historical_support = all_positive and validation_positive and clears_target
    classification = (
        "prospective_shadow_watchlist_historical_support_not_independent_proof"
        if historical_support
        else "remain_candidate_historical_support_insufficient"
    )
    return {
        "signal_id": "S-012",
        "registry_id": "BTC-QQQ-REALIZED-VOL-COMPRESSION-001",
        "audit_version": 1,
        "purpose": "Correct inferential overstatement from overlapping holding periods and duplicated year-matched benchmark rows while preserving every canonical trigger descriptively.",
        "historical_input_sha256": sha256_path(historical_input)
        if historical_input
        else None,
        "cost_assumption_round_trip_bps": cost_bps,
        "primary_horizon_calendar_days": PRIMARY_HORIZON,
        "prospective_untouched_boundary": PROSPECTIVE_BOUNDARY.isoformat(),
        "canonical_trigger_count": len(trigger_indices),
        "horizons": horizons,
        "decision": {
            "classification": classification,
            "historical_support": historical_support,
            "primary_nonoverlapping_event_count": all_count,
            "primary_source_exposed_validation_nonoverlapping_event_count": validation_count,
            "minimum_untouched_prospective_events_required": 10,
            "historical_sample_adequate_for_production": False,
            "reason": (
                "The 90-day historical pattern is positive versus the matched null, but fresh crossovers cluster and only a small number of nonoverlapping source-exposed validation episodes exist. Historical data can justify monitoring, not production."
                if historical_support
                else "The conservative nonoverlapping audit does not satisfy the frozen historical support conditions."
            ),
            "all_history_clears_25pct_target": clears_target,
            "source_exposed_validation_clears_25pct_target": validation_clears,
            "capital_rights": "none",
            "real_money_trading_authorized": False,
            "production_stage_permitted": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Conservative independence and matched-null audit for S-012"
    )
    parser.add_argument("--start", type=parse_date, default=DEFAULT_START)
    parser.add_argument("--end", type=parse_date, required=True)
    parser.add_argument("--cost-bps", type=float, default=ROUND_TRIP_COST_BPS)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/s012"))
    parser.add_argument("--historical-input", type=Path)
    parser.add_argument("--simulations", type=int, default=SIMULATIONS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.simulations < 1000:
        raise SystemExit("--simulations must be at least 1000")
    btc, qqq, sources = load_data(args.start, args.end, args.cache_dir, False)
    result = audit(
        btc,
        qqq,
        cost_bps=args.cost_bps,
        historical_input=args.historical_input,
        simulations=args.simulations,
    )
    result["data_sources"] = sources
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
