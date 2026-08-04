from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalStage(str, Enum):
    CANDIDATE = "candidate"
    HYPOTHESIS = "hypothesis"
    BACKTEST = "backtest"
    PRODUCTION = "production"
    RETIRED = "retired"


class OperationalStatus(str, Enum):
    UNSPECIFIED = "unspecified"
    READY_FOR_HYPOTHESIS = "ready_for_hypothesis"
    READY_FOR_DATA = "ready_for_data"
    BACKTEST_IN_PROGRESS = "backtest_in_progress"
    REJECTED = "rejected"
    WATCHLIST = "watchlist"
    PAPER_TRADING = "paper_trading"
    PRODUCTION = "production"
    DEGRADED = "degraded"
    DORMANT = "dormant"
    RETIRED = "retired"


@dataclass(frozen=True)
class ConfidenceEvidence:
    """Evidence used to update—not narratively override—a confidence score."""

    sample_size: int = 0
    out_of_sample_trades: int = 0
    out_of_sample_sharpe: float | None = None
    regime_coverage: float = 0.0
    implementation_cost_bps: float | None = None
    gross_edge_bps: float | None = None
    decay_risk: float = 1.0
    data_quality: float = 0.0


@dataclass(frozen=True)
class SignalCandidate:
    signal_id: str
    registry_id: str
    name: str
    family: str
    stage: SignalStage
    operational_status: OperationalStatus
    source_urls: tuple[str, ...]
    hypothesis: str
    predictor_assets: tuple[str, ...] = ()
    target_assets: tuple[str, ...] = ()
    horizon: str = ""
    applicable_regimes: tuple[str, ...] = ()
    invalid_regimes: tuple[str, ...] = ()
    mechanism: str = ""
    decay_mechanism: str = ""
    canonical_rule: str = ""
    deactivation_rule: str = ""
    benchmark: str = ""
    data_source: str = ""
    confidence_score: float = 0.0
    confidence_as_of: str = ""
    confidence_components: dict[str, float] = field(default_factory=dict)
    production_requirements: dict[str, bool] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SignalCandidate":
        payload = dict(raw)
        payload["stage"] = SignalStage(payload["stage"])
        payload["operational_status"] = OperationalStatus(
            payload.get("operational_status", "unspecified")
        )
        for key in (
            "source_urls",
            "predictor_assets",
            "target_assets",
            "applicable_regimes",
            "invalid_regimes",
            "aliases",
            "evidence_ids",
        ):
            payload[key] = tuple(payload.get(key, ()))
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON-compatible registry representation."""
        return {
            "signal_id": self.signal_id,
            "registry_id": self.registry_id,
            "name": self.name,
            "family": self.family,
            "stage": self.stage.value,
            "operational_status": self.operational_status.value,
            "source_urls": list(self.source_urls),
            "hypothesis": self.hypothesis,
            "predictor_assets": list(self.predictor_assets),
            "target_assets": list(self.target_assets),
            "horizon": self.horizon,
            "applicable_regimes": list(self.applicable_regimes),
            "invalid_regimes": list(self.invalid_regimes),
            "mechanism": self.mechanism,
            "decay_mechanism": self.decay_mechanism,
            "canonical_rule": self.canonical_rule,
            "deactivation_rule": self.deactivation_rule,
            "benchmark": self.benchmark,
            "data_source": self.data_source,
            "confidence_score": self.confidence_score,
            "confidence_as_of": self.confidence_as_of,
            "confidence_components": dict(self.confidence_components),
            "production_requirements": dict(self.production_requirements),
            "aliases": list(self.aliases),
            "evidence_ids": list(self.evidence_ids),
            "notes": self.notes,
            "metadata": dict(self.metadata),
        }
