"""Reusable signal research primitives.

The package deliberately separates a simple canonical signal from optional
enhancements.  A candidate must demonstrate predictive value out of sample
before weighting or optimization is promoted into production.
"""

from .models import ConfidenceEvidence, SignalCandidate, SignalStage
from .confidence import confidence_score
from .rebound import ReboundConfig, ReboundObservation, evaluate_rebound

__all__ = [
    "ConfidenceEvidence",
    "SignalCandidate",
    "SignalStage",
    "ReboundConfig",
    "ReboundObservation",
    "confidence_score",
    "evaluate_rebound",
]
