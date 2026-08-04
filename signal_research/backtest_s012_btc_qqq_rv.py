from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
DEFAULT_START = date(2014, 9, 17)
DEFAULT_END = date(2026, 8, 3)
PROSPECTIVE_BOUNDARY = date(2026, 8, 4)
DEVELOPMENT_END = date(2021, 12, 31)
LOOKBACK_DAYS = 30
HORIZONS = (30, 90, 180, 365)
ROUND_TRIP_COST_BPS = 20.0
BOOTSTRAP_SAMPLES = 5000
RANDOM_SEED = 12012


@dataclass(frozen=True)
class PricePoint:
    session_date: date
    close: float
    available_at: datetime


@dataclass(frozen=True)
class ComparableObservation:
    decision_date: date
    decision_at: datetime
    btc_close_date: date
    btc_close: float
    qqq_close: float
    btc_rv: float
    qqq_rv: float
    ratio: float
    regime: str


@dataclass(frozen=True)
class EventOutcome:
    trigger_date: date
    entry_date: date
    exit_date: date
    horizon: str
    split: str
    regime: str
    gross_return: float
    net_return: float
    max_adverse_excursion: float
    max_drawdown: float
    drawdown_10: bool
    drawdown_20: bool
    drawdown_30: bool


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def yahoo_url(symbol: str, start: date, end: date) -> str:
    period1 = int(datetime.combine(start, dt_time.min, tzinfo=UTC).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=2), dt_time.min, tzinfo=UTC).timestamp())
    query = urllib.parse.urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
    )
    return f"{YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol))}?{query}"


def fetch_json(url: str, cache_path: Path, *, refresh: bool = False) -> tuple[dict, str, str]:
    if cache_path.exists() and not refresh:
        payload = cache_path.read_bytes()
        return json.loads(payload), sha256_bytes(payload), "cache"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SignalsResearch/1.0; +https://github.com/Caleblucas1/polymarket-wti-snapshot)",
            "Accept": "application/json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            parsed = json.loads(payload)
            cache_path.write_bytes(payload)
            return parsed, sha256_bytes(payload), "network"
        except Exception as exc:  # pragma: no cover - network behavior
            last_error = exc
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def _chart_result(payload: dict) -> dict:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise ValueError("Yahoo response missing chart object")
    if chart.get("error"):
        raise ValueError(f"Yahoo chart error: {chart['error']}")
    rows = chart.get("result")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("Yahoo response must contain exactly one chart result")
    return rows[0]


def parse_btc_prices(payload: dict) -> list[PricePoint]:
    result = _chart_result(payload)
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    if len(timestamps) != len(closes):
        raise ValueError("BTC timestamp and close lengths differ")
    points: list[PricePoint] = []
    for raw_ts, raw_close in zip(timestamps, closes):
        if raw_close is None:
            continue
        start = datetime.fromtimestamp(int(raw_ts), tz=UTC)
        session = start.date()
        points.append(
            PricePoint(
                session_date=session,
                close=float(raw_close),
                available_at=datetime.combine(session + timedelta(days=1), dt_time.min, tzinfo=UTC),
            )
        )
    return sorted(points, key=lambda row: row.available_at)


def parse_qqq_prices(payload: dict) -> list[PricePoint]:
    result = _chart_result(payload)
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    adjusted = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
    quote_closes = ((indicators.get("quote") or [{}])[0]).get("close") or []
    closes = adjusted if len(adjusted) == len(timestamps) else quote_closes
    if len(timestamps) != len(closes):
        raise ValueError("QQQ timestamp and adjusted-close lengths differ")
    points: list[PricePoint] = []
    for raw_ts, raw_close in zip(timestamps, closes):
        if raw_close is None:
            continue
        stamp = datetime.fromtimestamp(int(raw_ts), tz=UTC).astimezone(NEW_YORK)
        session = stamp.date()
        decision = datetime.combine(session, dt_time(16, 0), tzinfo=NEW_YORK).astimezone(UTC)
        points.append(PricePoint(session, float(raw_close), decision))
    return sorted(points, key=lambda row: row.available_at)


def log_returns(points: Sequence[PricePoint]) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    for previous, current in zip(points, points[1:]):
        if previous.close <= 0 or current.close <= 0:
            raise ValueError("prices must be positive")
        rows.append((current.session_date, math.log(current.close / previous.close)))
    return rows


def realized_volatility(
    returns: Sequence[tuple[date, float]],
    end_date: date,
    *,
    lookback_days: int,
    annualization_days: int,
    minimum_observations: int,
) -> float | None:
    start_date = end_date - timedelta(days=lookback_days)
    values = [value for row_date, value in returns if start_date < row_date <= end_date]
    if len(values) < minimum_observations:
        return None
    return statistics.stdev(values) * math.sqrt(annualization_days)


def _latest_available(points: Sequence[PricePoint], cutoff: datetime) -> PricePoint | None:
    latest: PricePoint | None = None
    for point in points:
        if point.available_at <= cutoff:
            latest = point
        else:
            break
    return latest


def classify_regime(btc_points: Sequence[PricePoint], end_date: date) -> str:
    eligible = [point for point in btc_points if point.session_date <= end_date]
    if len(eligible) < 201:
        return "insufficient_history"
    current = eligible[-1].close
    ma200 = statistics.fmean(point.close for point in eligible[-200:])
    ninety_cutoff = end_date - timedelta(days=90)
    prior = max(
        (point for point in eligible if point.session_date <= ninety_cutoff),
        key=lambda row: row.session_date,
        default=None,
    )
    if prior is None:
        return "insufficient_history"
    momentum = current / prior.close - 1
    if current >= ma200 and momentum > 0:
        return "bull_expansion"
    if current < ma200 and momentum > 0:
        return "post_bear_accumulation"
    if current < ma200 and momentum <= 0:
        return "bear_contraction"
    return "late_bull_or_transition"


def build_comparable_observations(
    btc_points: Sequence[PricePoint],
    qqq_points: Sequence[PricePoint],
    *,
    lookback_days: int = LOOKBACK_DAYS,
) -> list[ComparableObservation]:
    btc_returns = log_returns(btc_points)
    qqq_returns = log_returns(qqq_points)
    observations: list[ComparableObservation] = []
    for qqq in qqq_points:
        btc = _latest_available(btc_points, qqq.available_at)
        if btc is None:
            continue
        btc_rv = realized_volatility(
            btc_returns,
            btc.session_date,
            lookback_days=lookback_days,
            annualization_days=365,
            minimum_observations=max(10, lookback_days - 5),
        )
        qqq_rv = realized_volatility(
            qqq_returns,
            qqq.session_date,
            lookback_days=lookback_days,
            annualization_days=252,
            minimum_observations=max(8, int(lookback_days * 0.45)),
        )
        if btc_rv is None or qqq_rv is None or qqq_rv <= 0:
            continue
        observations.append(
            ComparableObservation(
                decision_date=qqq.session_date,
                decision_at=qqq.available_at,
                btc_close_date=btc.session_date,
                btc_close=btc.close,
                qqq_close=qqq.close,
                btc_rv=btc_rv,
                qqq_rv=qqq_rv,
                ratio=btc_rv / qqq_rv,
                regime=classify_regime(btc_points, btc.session_date),
            )
        )
    return observations


def extract_trigger_indices(observations: Sequence[ComparableObservation]) -> list[int]:
    indices: list[int] = []
    armed = False
    for index, row in enumerate(observations):
        below = row.btc_rv < row.qqq_rv
        if not below:
            armed = True
            continue
        if armed:
            indices.append(index)
            armed = False
    return indices


def _first_point_after(points: Sequence[PricePoint], cutoff: datetime) -> PricePoint | None:
    for point in points:
        if point.available_at > cutoff:
            return point
    return None


def _first_point_on_or_after_date(points: Sequence[PricePoint], target: date) -> PricePoint | None:
    for point in points:
        if point.session_date >= target:
            return point
    return None


def _path(points: Sequence[PricePoint], start: date, end: date) -> list[PricePoint]:
    return [point for point in points if start <= point.session_date <= end]


def max_drawdown(prices: Sequence[float]) -> float:
    if not prices:
        return math.nan
    peak = prices[0]
    worst = 0.0
    for value in prices:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def split_name(trigger_date: date) -> str:
    if trigger_date <= DEVELOPMENT_END:
        return "development"
    if trigger_date < PROSPECTIVE_BOUNDARY:
        return "historical_validation_source_exposed"
    return "prospective_untouched"


def event_outcome(
    trigger_index: int,
    observations: Sequence[ComparableObservation],
    btc_points: Sequence[PricePoint],
    horizon: int | str,
    *,
    cost_bps: float = ROUND_TRIP_COST_BPS,
) -> EventOutcome | None:
    trigger = observations[trigger_index]
    entry = _first_point_after(btc_points, trigger.decision_at)
    if entry is None:
        return None
    if horizon == "crossover":
        exit_decision: ComparableObservation | None = None
        for row in observations[trigger_index + 1 :]:
            if row.btc_rv >= row.qqq_rv:
                exit_decision = row
                break
        if exit_decision is None:
            return None
        exit_point = _first_point_after(btc_points, exit_decision.decision_at)
    else:
        exit_point = _first_point_on_or_after_date(
            btc_points, entry.session_date + timedelta(days=int(horizon))
        )
    if exit_point is None or exit_point.session_date <= entry.session_date:
        return None
    path = _path(btc_points, entry.session_date, exit_point.session_date)
    relative = [point.close / entry.close - 1 for point in path]
    gross = exit_point.close / entry.close - 1
    net = gross - cost_bps / 10_000
    adverse = min(relative) if relative else math.nan
    return EventOutcome(
        trigger_date=trigger.decision_date,
        entry_date=entry.session_date,
        exit_date=exit_point.session_date,
        horizon=str(horizon),
        split=split_name(trigger.decision_date),
        regime=trigger.regime,
        gross_return=gross,
        net_return=net,
        max_adverse_excursion=adverse,
        max_drawdown=max_drawdown([point.close for point in path]),
        drawdown_10=adverse <= -0.10,
        drawdown_20=adverse <= -0.20,
        drawdown_30=adverse <= -0.30,
    )


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    location = (len(ordered) - 1) * probability
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    weight = location - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap_mean_ci(
    values: Sequence[float], samples: int = BOOTSTRAP_SAMPLES, seed: int = RANDOM_SEED
) -> list[float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(samples)]
    return [percentile(means, 0.025), percentile(means, 0.975)]


def summarize_outcomes(rows: Sequence[EventOutcome]) -> dict:
    if not rows:
        return {"event_count": 0}
    net = [row.net_return for row in rows]
    gross = [row.gross_return for row in rows]
    mean = statistics.fmean(net)
    stdev = statistics.stdev(net) if len(net) > 1 else 0.0
    return {
        "event_count": len(rows),
        "mean_gross_return": statistics.fmean(gross),
        "median_gross_return": statistics.median(gross),
        "mean_net_return": mean,
        "median_net_return": statistics.median(net),
        "hit_rate_net_positive": sum(value > 0 for value in net) / len(net),
        "event_sharpe": mean / stdev if stdev > 0 else None,
        "bootstrap_95pct_mean_net_ci": bootstrap_mean_ci(net),
        "mean_max_adverse_excursion": statistics.fmean(
            row.max_adverse_excursion for row in rows
        ),
        "worst_max_adverse_excursion": min(row.max_adverse_excursion for row in rows),
        "mean_path_max_drawdown": statistics.fmean(row.max_drawdown for row in rows),
        "worst_path_max_drawdown": min(row.max_drawdown for row in rows),
        "subsequent_drawdown_10_rate": sum(row.drawdown_10 for row in rows) / len(rows),
        "subsequent_drawdown_20_rate": sum(row.drawdown_20 for row in rows) / len(rows),
        "subsequent_drawdown_30_rate": sum(row.drawdown_30 for row in rows) / len(rows),
    }


def benchmark_outcomes(
    observations: Sequence[ComparableObservation],
    btc_points: Sequence[PricePoint],
    horizon: int,
    *,
    cost_bps: float,
) -> list[EventOutcome]:
    rows: list[EventOutcome] = []
    for index, _ in enumerate(observations):
        outcome = event_outcome(index, observations, btc_points, horizon, cost_bps=cost_bps)
        if outcome is not None:
            rows.append(outcome)
    return rows


def matched_benchmark(
    trigger_rows: Sequence[EventOutcome], all_rows: Sequence[EventOutcome]
) -> list[EventOutcome]:
    by_year: dict[int, list[EventOutcome]] = {}
    for row in all_rows:
        by_year.setdefault(row.trigger_date.year, []).append(row)
    matched: list[EventOutcome] = []
    for trigger in trigger_rows:
        matched.extend(by_year.get(trigger.trigger_date.year, []))
    return matched


def improvement(trigger_summary: dict, benchmark_summary: dict) -> dict:
    trigger_mean = trigger_summary.get("mean_net_return")
    benchmark_mean = benchmark_summary.get("mean_net_return")
    if trigger_mean is None or benchmark_mean is None:
        return {}
    absolute = trigger_mean - benchmark_mean
    relative = absolute / abs(benchmark_mean) if abs(benchmark_mean) > 1e-12 else None
    return {
        "absolute_mean_net_return_edge": absolute,
        "relative_improvement_vs_abs_benchmark_mean": relative,
        "clears_25pct_conditional_improvement_target": relative is not None and relative >= 0.25,
    }


def serialize_event(row: EventOutcome) -> dict:
    return {
        "trigger_date": row.trigger_date.isoformat(),
        "entry_date": row.entry_date.isoformat(),
        "exit_date": row.exit_date.isoformat(),
        "horizon": row.horizon,
        "split": row.split,
        "regime": row.regime,
        "gross_return": row.gross_return,
        "net_return": row.net_return,
        "max_adverse_excursion": row.max_adverse_excursion,
        "max_drawdown": row.max_drawdown,
        "drawdown_10": row.drawdown_10,
        "drawdown_20": row.drawdown_20,
        "drawdown_30": row.drawdown_30,
    }


def run_backtest(
    btc_points: Sequence[PricePoint],
    qqq_points: Sequence[PricePoint],
    *,
    cost_bps: float = ROUND_TRIP_COST_BPS,
) -> dict:
    observations = build_comparable_observations(btc_points, qqq_points)
    trigger_indices = extract_trigger_indices(observations)
    by_horizon: dict[str, dict] = {}
    for horizon in (*HORIZONS, "crossover"):
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
        split_rows: dict[str, list[EventOutcome]] = {}
        regime_rows: dict[str, list[EventOutcome]] = {}
        for row in events:
            split_rows.setdefault(row.split, []).append(row)
            regime_rows.setdefault(row.regime, []).append(row)
        payload: dict = {
            "summary": summarize_outcomes(events),
            "by_split": {
                key: summarize_outcomes(value) for key, value in sorted(split_rows.items())
            },
            "by_regime": {
                key: summarize_outcomes(value) for key, value in sorted(regime_rows.items())
            },
            "events": [serialize_event(row) for row in events],
        }
        if isinstance(horizon, int):
            all_rows = benchmark_outcomes(
                observations, btc_points, horizon, cost_bps=cost_bps
            )
            matched = matched_benchmark(events, all_rows)
            benchmark_summary = summarize_outcomes(matched)
            payload["calendar_year_matched_unconditional_benchmark"] = benchmark_summary
            payload["improvement"] = improvement(payload["summary"], benchmark_summary)
        by_horizon[str(horizon)] = payload

    latest = observations[-1] if observations else None
    complete_horizon = by_horizon["90"]["summary"]
    validation_90 = by_horizon["90"]["by_split"].get(
        "historical_validation_source_exposed", {"event_count": 0}
    )
    sample_adequate = complete_horizon.get("event_count", 0) >= 10
    validation_positive = validation_90.get("mean_net_return", 0) > 0
    validation_ci = validation_90.get("bootstrap_95pct_mean_net_ci")
    validation_ci_positive = bool(validation_ci and validation_ci[0] > 0)
    improvement_90 = by_horizon["90"].get("improvement", {})
    decision = {
        "research_cycle_classification": (
            "advance_to_prospective_shadow_watchlist"
            if sample_adequate and validation_positive
            else "remain_candidate_or_reject"
        ),
        "sample_adequate_at_90_days": sample_adequate,
        "historical_validation_mean_net_positive_at_90_days": validation_positive,
        "historical_validation_ci_excludes_zero_at_90_days": validation_ci_positive,
        "clears_25pct_improvement_target_at_90_days": improvement_90.get(
            "clears_25pct_conditional_improvement_target", False
        ),
        "capital_rights": "none",
        "real_money_trading_authorized": False,
        "production_stage_permitted": False,
        "reason_production_is_blocked": "No untouched prospective outcomes exist after the frozen 2026-08-04 boundary.",
    }
    return {
        "signal_id": "S-012",
        "registry_id": "BTC-QQQ-REALIZED-VOL-COMPRESSION-001",
        "generated_at": iso_z(datetime.now(tz=UTC)),
        "canonical_definition": {
            "lookback_calendar_days": LOOKBACK_DAYS,
            "btc_annualization_days": 365,
            "qqq_annualization_days": 252,
            "entry": "first BTC UTC daily close strictly after the QQQ-close decision timestamp",
            "round_trip_cost_bps": cost_bps,
            "development_end": DEVELOPMENT_END.isoformat(),
            "prospective_untouched_boundary": PROSPECTIVE_BOUNDARY.isoformat(),
        },
        "observation_count": len(observations),
        "trigger_count": len(trigger_indices),
        "first_comparable_date": observations[0].decision_date.isoformat()
        if observations
        else None,
        "last_comparable_date": observations[-1].decision_date.isoformat()
        if observations
        else None,
        "latest_state": (
            {
                "decision_date": latest.decision_date.isoformat(),
                "btc_rv": latest.btc_rv,
                "qqq_rv": latest.qqq_rv,
                "ratio": latest.ratio,
                "below": latest.btc_rv < latest.qqq_rv,
                "regime": latest.regime,
            }
            if latest
            else None
        ),
        "horizons": by_horizon,
        "decision": decision,
        "source_chart_reproduction": {
            "status": "not_exactly_verifiable_from_image_only",
            "explanation": "The supplied chart does not expose machine-readable marker timestamps or indicator source code. This implementation reproduces the frozen canonical crossover independently and does not claim that every source marker used identical rules.",
        },
    }


def validate_prices(points: Sequence[PricePoint], name: str) -> list[str]:
    errors: list[str] = []
    if not points:
        return [f"{name}: no prices"]
    dates = [point.session_date for point in points]
    if dates != sorted(dates):
        errors.append(f"{name}: dates are not sorted")
    if len(dates) != len(set(dates)):
        errors.append(f"{name}: duplicate dates")
    if any(point.close <= 0 or not math.isfinite(point.close) for point in points):
        errors.append(f"{name}: invalid close")
    if any(point.available_at.tzinfo is None for point in points):
        errors.append(f"{name}: naive availability timestamp")
    return errors


def load_data(
    start: date, end: date, cache_dir: Path, refresh: bool
) -> tuple[list[PricePoint], list[PricePoint], dict]:
    sources: dict = {}
    btc_url = yahoo_url("BTC-USD", start - timedelta(days=60), end)
    qqq_url = yahoo_url("QQQ", start - timedelta(days=60), end)
    btc_raw, btc_hash, btc_mode = fetch_json(
        btc_url, cache_dir / "BTC-USD.json", refresh=refresh
    )
    qqq_raw, qqq_hash, qqq_mode = fetch_json(
        qqq_url, cache_dir / "QQQ.json", refresh=refresh
    )
    btc = [
        point
        for point in parse_btc_prices(btc_raw)
        if start - timedelta(days=60) <= point.session_date <= end
    ]
    qqq = [
        point
        for point in parse_qqq_prices(qqq_raw)
        if start - timedelta(days=60) <= point.session_date <= end
    ]
    errors = [*validate_prices(btc, "BTC"), *validate_prices(qqq, "QQQ")]
    if errors:
        raise ValueError("; ".join(errors))
    sources["BTC-USD"] = {
        "url": btc_url,
        "sha256": btc_hash,
        "retrieval": btc_mode,
        "rows": len(btc),
    }
    sources["QQQ"] = {
        "url": qqq_url,
        "sha256": qqq_hash,
        "retrieval": qqq_mode,
        "rows": len(qqq),
    }
    return btc, qqq, sources


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest S-012 BTC realized-volatility compression below QQQ"
    )
    parser.add_argument("--start", type=parse_date, default=DEFAULT_START)
    parser.add_argument("--end", type=parse_date, default=DEFAULT_END)
    parser.add_argument("--cost-bps", type=float, default=ROUND_TRIP_COST_BPS)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/s012"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.start >= args.end:
        raise SystemExit("--start must be before --end")
    if args.cost_bps < 0:
        raise SystemExit("--cost-bps must be nonnegative")
    btc, qqq, sources = load_data(args.start, args.end, args.cache_dir, args.refresh)
    result = run_backtest(btc, qqq, cost_bps=args.cost_bps)
    result["data_sources"] = sources
    result["requested_period"] = {
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "trigger_count": result["trigger_count"],
                "decision": result["decision"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
