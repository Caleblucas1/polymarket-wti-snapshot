from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtest_s010_btc_time_of_day import (
    HORIZONS,
    Bar,
    download_month,
    month_keys,
    parse_archive,
    run,
)

WINDOW_DAYS = (7, 14, 21, 30, 60, 90)


def _iso_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()


def _slice_bars(bars: list[Bar], start: datetime, end: datetime) -> list[Bar]:
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    return [bar for bar in bars if start_ms <= bar.open_time_ms <= end_ms]


def _hour_cross_section(result: dict, horizon: int) -> tuple[float, float, float, int]:
    key = f"{horizon}h"
    values = [
        result["hour_horizon_matrix"][f"{hour:02d}:00"][key].get("mean_net", math.nan)
        for hour in range(24)
    ]
    target = values[20]
    valid = [value for value in values if math.isfinite(value)]
    average = statistics.fmean(valid) if valid else math.nan
    median = statistics.median(valid) if valid else math.nan
    ranked = sorted(enumerate(values), key=lambda item: item[1], reverse=True)
    rank = next(index + 1 for index, item in enumerate(ranked) if item[0] == 20)
    return target, average, median, rank


def summarize_window(bars: list[Bar], start: datetime, end: datetime, cost_bps: float) -> dict:
    result = run(bars, _iso_date(start), _iso_date(end), cost_bps)
    horizons: dict[str, dict] = {}
    for horizon in HORIZONS:
        target, average, median, rank = _hour_cross_section(result, horizon)
        cell = result["hour_horizon_matrix"]["20:00"][f"{horizon}h"]
        horizons[f"{horizon}h"] = {
            "n": cell.get("n", 0),
            "mean_gross": cell.get("mean_gross"),
            "mean_net": target,
            "median_gross": cell.get("median_gross"),
            "hit_rate_after_cost": cell.get("hit_rate"),
            "all_hour_mean_net": average,
            "all_hour_median_net": median,
            "excess_vs_all_hour_mean": target - average,
            "rank_among_24_hours": rank,
        }
    low = result["local_low_diagnostic"]["20:00"]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bar_count": result["bar_count"],
        "missing_hour_gaps": len(result["missing_hour_gaps"]),
        "horizons": horizons,
        "local_low_diagnostic": low,
    }


def build_rolling_analysis(
    bars: list[Bar],
    sample_start: datetime,
    sample_end: datetime,
    cost_bps: float,
) -> dict:
    endpoint_windows: dict[str, dict] = {}
    rolling_history: dict[str, list[dict]] = {}

    for days in WINDOW_DAYS:
        window_start = sample_end - timedelta(days=days) + timedelta(hours=1)
        endpoint_windows[f"{days}d"] = summarize_window(
            _slice_bars(bars, window_start, sample_end), window_start, sample_end, cost_bps
        )

        rows: list[dict] = []
        first_end = sample_start + timedelta(days=days) - timedelta(hours=1)
        cursor = first_end
        while cursor <= sample_end:
            start = cursor - timedelta(days=days) + timedelta(hours=1)
            subset = _slice_bars(bars, start, cursor)
            if subset:
                summary = summarize_window(subset, start, cursor, cost_bps)
                rows.append({
                    "end": cursor.isoformat(),
                    "horizons": summary["horizons"],
                    "local_low_diagnostic": summary["local_low_diagnostic"],
                })
            cursor += timedelta(days=1)
        rolling_history[f"{days}d"] = rows

    return {
        "signal_id": "BTC-TOD-2000-UTC-001",
        "legacy_label": "S-010-time-of-day",
        "analysis": "rolling_recent_regime",
        "research_only": True,
        "real_money_trading_authorized": False,
        "confirmatory_hour_utc": 20,
        "window_days": list(WINDOW_DAYS),
        "horizons_hours": list(HORIZONS),
        "round_trip_cost_bps": cost_bps,
        "sample_start": sample_start.isoformat(),
        "sample_end": sample_end.isoformat(),
        "endpoint_windows": endpoint_windows,
        "daily_rolling_history": rolling_history,
        "interpretation_rule": {
            "support_requires": "20:00 UTC must outperform the cross-hour mean after costs, rank in the top six of 24 hours, and show local-low concentration in more than one adjacent recent window.",
            "contradiction": "Positive absolute BTC return without relative hourly outperformance does not support the timing signal.",
            "exploratory_outputs": "Any other strong or weak hour discovered in the full matrix requires a new untouched confirmation period."
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--cost-bps", type=float, default=14.0)
    parser.add_argument("--cache-dir", default=".cache/binance_btc_1h")
    parser.add_argument("--output", default="artifacts/S010_BTC_ROLLING_REGIMES.json")
    args = parser.parse_args()

    bars: list[Bar] = []
    for key in month_keys(args.start, args.end):
        bars.extend(parse_archive(download_month(key, Path(args.cache_dir))))
    bars.sort(key=lambda bar: bar.open_time_ms)
    if not bars:
        raise RuntimeError("no bars loaded")

    sample_start = datetime.fromtimestamp(bars[0].open_time_ms / 1000, tz=timezone.utc)
    sample_end = datetime.fromtimestamp(bars[-1].open_time_ms / 1000, tz=timezone.utc)
    result = build_rolling_analysis(bars, sample_start, sample_end, args.cost_bps)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "sample_end": result["sample_end"],
        "endpoint_windows": result["endpoint_windows"],
    }, indent=2))


if __name__ == "__main__":
    main()
