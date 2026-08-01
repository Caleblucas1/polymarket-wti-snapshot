from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from statistics import fmean, pstdev
from typing import Iterable


@dataclass(frozen=True)
class TradeResult:
    signal_id: str
    timestamp: str
    gross_return: float
    cost_return: float = 0.0
    benchmark_return: float = 0.0
    regime: str = "unclassified"
    direction_correct: bool | None = None
    out_of_sample: bool = False

    @property
    def net_return(self) -> float:
        return self.gross_return - self.cost_return

    @property
    def abnormal_return(self) -> float:
        return self.net_return - self.benchmark_return


@dataclass(frozen=True)
class BacktestMetrics:
    observations: int
    hit_rate: float | None
    mean_net_return: float
    mean_abnormal_return: float
    sharpe_per_observation: float | None
    total_net_return: float
    max_drawdown: float


def summarize(results: Iterable[TradeResult]) -> BacktestMetrics:
    rows = list(results)
    if not rows:
        return BacktestMetrics(0, None, 0.0, 0.0, None, 0.0, 0.0)

    net = [row.net_return for row in rows]
    abnormal = [row.abnormal_return for row in rows]
    scored = [row.direction_correct for row in rows if row.direction_correct is not None]
    hit_rate = sum(bool(value) for value in scored) / len(scored) if scored else None
    dispersion = pstdev(net)
    sharpe = fmean(net) / dispersion * sqrt(len(net)) if dispersion > 0 else None

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in net:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)

    return BacktestMetrics(
        observations=len(rows),
        hit_rate=hit_rate,
        mean_net_return=fmean(net),
        mean_abnormal_return=fmean(abnormal),
        sharpe_per_observation=sharpe,
        total_net_return=equity - 1.0,
        max_drawdown=max_drawdown,
    )


def summarize_by_regime(results: Iterable[TradeResult]) -> dict[str, BacktestMetrics]:
    grouped: dict[str, list[TradeResult]] = defaultdict(list)
    for result in results:
        grouped[result.regime].append(result)
    return {regime: summarize(rows) for regime, rows in sorted(grouped.items())}
