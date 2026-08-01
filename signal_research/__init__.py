"""Reusable signal-research and governance primitives.

The package asks whether a signal can earn and keep the right to influence
capital allocation. Candidates remain research-only until fixed rules, costs,
regime tests, out-of-sample evidence and deactivation controls pass the
production gate.
"""

from .confidence import confidence_score
from .governance import (
    CONFIDENCE_WEIGHTS,
    PRODUCTION_CONFIDENCE_THRESHOLD,
    capital_rights,
    component_confidence_score,
    confidence_band,
    family_health,
    production_gate,
)
from .models import (
    ConfidenceEvidence,
    OperationalStatus,
    SignalCandidate,
    SignalStage,
)
from .rebound import ReboundConfig, ReboundObservation, evaluate_rebound

__all__ = [
    "CONFIDENCE_WEIGHTS",
    "PRODUCTION_CONFIDENCE_THRESHOLD",
    "ConfidenceEvidence",
    "OperationalStatus",
    "SignalCandidate",
    "SignalStage",
    "ReboundConfig",
    "ReboundObservation",
    "capital_rights",
    "component_confidence_score",
    "confidence_band",
    "confidence_score",
    "evaluate_rebound",
    "family_health",
    "production_gate",
]
