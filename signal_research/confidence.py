from __future__ import annotations

import math

from .models import ConfidenceEvidence


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def confidence_score(evidence: ConfidenceEvidence) -> float:
    """Return a conservative 0-100 research confidence score.

    The score rewards out-of-sample evidence, usable sample size, regime
    coverage, and data quality. It penalizes costs that consume the measured
    edge and high decay risk. Missing evidence remains a penalty rather than
    being filled with optimistic defaults.
    """

    sample = 1.0 - math.exp(-max(evidence.sample_size, 0) / 100.0)
    oos_sample = 1.0 - math.exp(-max(evidence.out_of_sample_trades, 0) / 50.0)
    sharpe = 0.0
    if evidence.out_of_sample_sharpe is not None:
        sharpe = _clamp((evidence.out_of_sample_sharpe + 0.25) / 2.25)

    net_edge = 0.0
    if evidence.gross_edge_bps is not None and evidence.implementation_cost_bps is not None:
        gross = max(abs(evidence.gross_edge_bps), 1e-9)
        net_edge = _clamp((evidence.gross_edge_bps - evidence.implementation_cost_bps) / gross)

    positive = (
        0.15 * sample
        + 0.25 * oos_sample
        + 0.20 * sharpe
        + 0.15 * _clamp(evidence.regime_coverage)
        + 0.15 * _clamp(evidence.data_quality)
        + 0.10 * net_edge
    )
    decay_multiplier = 1.0 - 0.55 * _clamp(evidence.decay_risk)
    return round(100.0 * positive * decay_multiplier, 1)
