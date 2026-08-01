from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HORIZONS = (1, 2, 4, 8, 12, 24, 48, 96, 168)
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h"


@dataclass(frozen=True)
class Bar:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.open_time_ms / 1000, tz=timezone.utc)


def month_keys(start: str, end: str) -> list[str]:
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    year, month = start_dt.year, start_dt.month
    keys: list[str] = []
    while (year, month) <= (end_dt.year, end_dt.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return keys


def download_month(key: str, cache_dir: Path) -> bytes:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"BTCUSDT-1h-{key}.zip"
    if path.exists():
        return path.read_bytes()
    url = f"{BASE_URL}/BTCUSDT-1h-{key}.zip"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"missing Binance archive {url}: HTTP {exc.code}") from exc
    path.write_bytes(payload)
    return payload


def parse_archive(payload: bytes) -> list[Bar]:
    bars: list[Bar] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"expected one CSV in archive, found {names}")
        with archive.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            for row in reader:
                if not row or not row[0].isdigit():
                    continue
                bars.append(
                    Bar(
                        open_time_ms=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                    )
                )
    return bars


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    if lo == hi:
        return ordered[lo]
    weight = index - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def summarize(values: list[float], round_trip_cost_bps: float) -> dict[str, float | int]:
    if not values:
        return {"n": 0}
    mean = statistics.fmean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    se = stdev / math.sqrt(len(values)) if values else math.nan
    cost = round_trip_cost_bps / 10_000
    return {
        "n": len(values),
        "mean_gross": mean,
        "median_gross": median,
        "mean_net": mean - cost,
        "hit_rate": sum(value > cost for value in values) / len(values),
        "standard_error": se,
        "ci95_low": mean - 1.96 * se,
        "ci95_high": mean + 1.96 * se,
        "p10": percentile(values, 0.10),
        "p90": percentile(values, 0.90),
    }


def run(bars: list[Bar], start: str, end: str, cost_bps: float) -> dict:
    start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() * 1000)
    bars = [bar for bar in bars if start_ms <= bar.open_time_ms <= end_ms]
    bars.sort(key=lambda bar: bar.open_time_ms)
    expected = 3_600_000
    gaps = [
        {"left": bars[i - 1].dt.isoformat(), "right": bars[i].dt.isoformat()}
        for i in range(1, len(bars))
        if bars[i].open_time_ms - bars[i - 1].open_time_ms != expected
    ]
    returns: dict[tuple[int, int], list[float]] = defaultdict(list)
    weekday_returns: dict[tuple[int, int, int], list[float]] = defaultdict(list)
    local_low_positions: dict[int, list[float]] = defaultdict(list)

    for i, bar in enumerate(bars):
        hour = bar.dt.hour
        weekday = bar.dt.weekday()
        for horizon in HORIZONS:
            j = i + horizon
            if j >= len(bars):
                continue
            exit_bar = bars[j]
            if exit_bar.open_time_ms - bar.open_time_ms != horizon * expected:
                continue
            value = exit_bar.open / bar.open - 1
            returns[(hour, horizon)].append(value)
            weekday_returns[(weekday, hour, horizon)].append(value)
        if 12 <= i < len(bars) - 12:
            window = bars[i - 12 : i + 13]
            low = min(item.low for item in window)
            high = max(item.high for item in window)
            position = 0.0 if high == low else (bar.open - low) / (high - low)
            local_low_positions[hour].append(position)

    matrix = {
        f"{hour:02d}:00": {
            f"{horizon}h": summarize(returns[(hour, horizon)], cost_bps)
            for horizon in HORIZONS
        }
        for hour in range(24)
    }
    weekday_matrix = {
        str(weekday): {
            f"{hour:02d}:00": {
                f"{horizon}h": summarize(weekday_returns[(weekday, hour, horizon)], cost_bps)
                for horizon in HORIZONS
            }
            for hour in range(24)
        }
        for weekday in range(7)
    }
    low_diag = {
        f"{hour:02d}:00": {
            "n": len(local_low_positions[hour]),
            "median_range_position": statistics.median(local_low_positions[hour])
            if local_low_positions[hour]
            else math.nan,
            "share_bottom_quartile": sum(x <= 0.25 for x in local_low_positions[hour])
            / len(local_low_positions[hour])
            if local_low_positions[hour]
            else math.nan,
        }
        for hour in range(24)
    }

    rankings = {}
    for horizon in HORIZONS:
        ranked = sorted(
            (
                (hour, matrix[f"{hour:02d}:00"][f"{horizon}h"].get("mean_net", math.nan))
                for hour in range(24)
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        rankings[f"{horizon}h"] = {
            "best": ranked[:5],
            "worst": ranked[-5:],
            "hour_20_rank": next(i + 1 for i, item in enumerate(ranked) if item[0] == 20),
        }

    return {
        "signal_id": "BTC-TOD-2000-UTC-001",
        "legacy_label": "S-010-time-of-day",
        "research_only": True,
        "real_money_trading_authorized": False,
        "data_source": "Binance public spot monthly BTCUSDT 1h kline archives",
        "start": start,
        "end": end,
        "bar_count": len(bars),
        "missing_hour_gaps": gaps,
        "round_trip_cost_bps": cost_bps,
        "confirmatory_hour_utc": 20,
        "robustness_hours_utc": [19, 21],
        "horizons_hours": list(HORIZONS),
        "hour_horizon_matrix": matrix,
        "weekday_hour_horizon_matrix": weekday_matrix,
        "local_low_diagnostic": low_diag,
        "rankings_by_horizon": rankings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--cost-bps", type=float, default=14.0)
    parser.add_argument("--cache-dir", default=".cache/binance_btc_1h")
    parser.add_argument("--output", default="signal_records/backtests/S010_BTC_TIME_OF_DAY.json")
    args = parser.parse_args()

    bars: list[Bar] = []
    for key in month_keys(args.start, args.end):
        bars.extend(parse_archive(download_month(key, Path(args.cache_dir))))
    result = run(bars, args.start, args.end, args.cost_bps)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "bar_count": result["bar_count"],
        "gaps": len(result["missing_hour_gaps"]),
        "20utc": result["hour_horizon_matrix"]["20:00"],
        "rankings": result["rankings_by_horizon"],
    }, indent=2))


if __name__ == "__main__":
    main()
