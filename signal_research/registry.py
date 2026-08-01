from __future__ import annotations

import json
from pathlib import Path

from .models import SignalCandidate


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "signal_candidates.json"


def load_candidates(path: str | Path = DEFAULT_REGISTRY) -> list[SignalCandidate]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported signal registry schema")
    candidates = [SignalCandidate.from_dict(item) for item in raw["signals"]]
    ids = [candidate.signal_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("signal IDs must be unique")
    return candidates


def get_candidate(signal_id: str, path: str | Path = DEFAULT_REGISTRY) -> SignalCandidate:
    for candidate in load_candidates(path):
        if candidate.signal_id == signal_id:
            return candidate
    raise KeyError(signal_id)
