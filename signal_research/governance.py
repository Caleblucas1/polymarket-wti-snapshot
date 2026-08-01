from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable

from .models import OperationalStatus, SignalCandidate, SignalStage

CONFIDENCE_WEIGHTS = {
    "statistical_evidence": 25.0,
    "out_of_sample_evidence": 20.0,
    "economic_mechanism": 15.0,
    "regime_clarity": 10.0,
    "execution_quality": 10.0,
    "robustness": 10.0,
    "current_relevance": 10.0,
}
PRODUCTION_CONFIDENCE_THRESHOLD = 60.0
REQUIRED_PRODUCTION_CHECKS = (
    "executable_rule",
    "out_of_sample_evidence",
    "costs_and_slippage",
    "regime_definition",
    "deactivation_rule",
    "validated_data_source",
    "lookahead_review",
)


@dataclass(frozen=True)
class ProductionGateResult:
    eligible_for_promotion: bool
    valid_current_production: bool
    checks: dict[str, bool]
    failures: tuple[str, ...]


def component_confidence_score(components: dict[str, float]) -> float:
    unknown = set(components) - set(CONFIDENCE_WEIGHTS)
    if unknown:
        raise ValueError(f"unknown confidence components: {sorted(unknown)}")
    score = 0.0
    for name, maximum in CONFIDENCE_WEIGHTS.items():
        value = float(components.get(name, 0.0))
        if not 0.0 <= value <= maximum:
            raise ValueError(f"{name} must be between 0 and {maximum:g}")
        score += value
    return round(score, 1)


def confidence_band(score: float) -> str:
    if not 0.0 <= score <= 100.0:
        raise ValueError("confidence score must be between 0 and 100")
    if score < 20:
        return "speculative"
    if score < 40:
        return "preliminary"
    if score < 60:
        return "promising"
    if score < 75:
        return "validated"
    if score < 90:
        return "strong"
    return "exceptional"


def production_gate(candidate: SignalCandidate) -> ProductionGateResult:
    checks = {
        "confidence_threshold": candidate.confidence_score >= PRODUCTION_CONFIDENCE_THRESHOLD,
        **{
            name: bool(candidate.production_requirements.get(name, False))
            for name in REQUIRED_PRODUCTION_CHECKS
        },
    }
    failures = tuple(name for name, passed in checks.items() if not passed)
    eligible = not failures
    valid_current = (
        candidate.stage is SignalStage.PRODUCTION
        and candidate.operational_status is OperationalStatus.PRODUCTION
        and eligible
    )
    return ProductionGateResult(eligible, valid_current, checks, failures)


def capital_rights(candidate: SignalCandidate) -> str:
    blocked = {
        OperationalStatus.REJECTED,
        OperationalStatus.DEGRADED,
        OperationalStatus.DORMANT,
        OperationalStatus.RETIRED,
    }
    if candidate.stage is SignalStage.RETIRED or candidate.operational_status in blocked:
        return "none"
    if production_gate(candidate).valid_current_production:
        return "capped_live"
    if candidate.stage is SignalStage.BACKTEST or candidate.operational_status is OperationalStatus.PAPER_TRADING:
        return "paper_only"
    return "research_only"


def family_health(candidates: Iterable[SignalCandidate]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[SignalCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.family, []).append(candidate)
    output = {}
    for family, members in sorted(grouped.items()):
        output[family] = {
            "signals": len(members),
            "mean_confidence": round(fmean(item.confidence_score for item in members), 1),
            "live_capable": sum(capital_rights(item) == "capped_live" for item in members),
        }
    return output
