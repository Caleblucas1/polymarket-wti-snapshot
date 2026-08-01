from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Sequence


@dataclass(frozen=True)
class ReboundConfig:
    volatility_lookback: int = 21
    reversal_sigma: float = 0.50
    reclaim_tolerance_sigma: float = 0.05
    trend_window: int = 5
    sustain_bars: int = 6
    retest_tolerance_sigma: float = 0.20

    def __post_init__(self) -> None:
        if not 2 <= self.volatility_lookback <= 30:
            raise ValueError("volatility_lookback must be between 2 and 30 bars")
        if self.trend_window < 2:
            raise ValueError("trend_window must be at least 2")
        if self.sustain_bars < 1:
            raise ValueError("sustain_bars must be positive")


@dataclass(frozen=True)
class ReboundObservation:
    realized_volatility: float
    local_low_reversal: bool
    reference_level_reclaim: bool
    trend_confirmation: bool
    sustained_recovery: bool

    @property
    def score(self) -> int:
        return sum(
            (
                self.local_low_reversal,
                self.reference_level_reclaim,
                self.trend_confirmation,
                self.sustained_recovery,
            )
        )

    @property
    def stage(self) -> str:
        return ("none", "early", "provisional", "confirmed", "full")[self.score]


def _returns(prices: Sequence[float]) -> list[float]:
    if len(prices) < 2:
        return []
    values: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        if previous <= 0 or current <= 0:
            raise ValueError("prices must be positive")
        values.append(current / previous - 1.0)
    return values


def evaluate_rebound(
    prices: Sequence[float],
    *,
    reference_level: float,
    config: ReboundConfig | None = None,
) -> ReboundObservation:
    """Evaluate all four rebound definitions for one asset.

    `prices` must end at the decision timestamp and must contain no future
    observations. Volatility is estimated only from the trailing configured
    lookback and can never exceed 30 bars. The result deliberately contains no
    cross-asset weighting; basket aggregation is deferred until the canonical
    signal demonstrates out-of-sample value.
    """

    cfg = config or ReboundConfig()
    minimum = max(cfg.volatility_lookback + 1, cfg.trend_window + 1, cfg.sustain_bars + 1)
    if len(prices) < minimum:
        raise ValueError(f"at least {minimum} prices are required")
    if reference_level <= 0:
        raise ValueError("reference_level must be positive")

    recent = list(prices[-(cfg.volatility_lookback + 1) :])
    volatility = pstdev(_returns(recent))
    volatility = max(volatility, 1e-9)

    current = prices[-1]
    local_low = min(prices)
    reversal_return = current / local_low - 1.0
    local_low_reversal = reversal_return >= cfg.reversal_sigma * volatility

    reclaim_return = current / reference_level - 1.0
    reference_level_reclaim = reclaim_return >= -cfg.reclaim_tolerance_sigma * volatility

    trend_slice = prices[-cfg.trend_window :]
    trend_average = sum(trend_slice) / len(trend_slice)
    prior_slice = prices[-cfg.trend_window - 1 : -1]
    prior_average = sum(prior_slice) / len(prior_slice)
    trend_confirmation = current >= trend_average and trend_average > prior_average

    sustain_slice = prices[-cfg.sustain_bars :]
    permitted_retest = local_low * (1.0 + cfg.retest_tolerance_sigma * volatility)
    sustained_recovery = min(sustain_slice) > permitted_retest and current > sustain_slice[0]

    return ReboundObservation(
        realized_volatility=volatility,
        local_low_reversal=local_low_reversal,
        reference_level_reclaim=reference_level_reclaim,
        trend_confirmation=trend_confirmation,
        sustained_recovery=sustained_recovery,
    )
