#!/usr/bin/env python3
"""Durable review records for the active exact-contract signal layer.

The market observation is evidence.  A user's rating is an annotation on that
evidence.  Keeping those layers separate makes it possible to learn from
ratings without silently changing contract definitions or historical odds.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from signal_contracts import validate_exact_signal_rows

SIGNAL_REVIEW_SCHEMA_VERSION = 2
SIGNAL_DEFINITION_VERSION = "all-active-contracts-v1"
DEFAULT_OBSERVATION_PATH = (
    Path(__file__).resolve().parent / "signal_records" / "observations.jsonl"
)

RATING_OPTIONS = (
    ("much_more_bullish", "Much more bullish"),
    ("more_bullish", "More bullish"),
    ("unchanged", "Unchanged"),
    ("more_bearish", "More bearish"),
    ("much_more_bearish", "Much more bearish"),
    ("conflicted", "Conflicted / mixed"),
    ("insufficient_evidence", "Insufficient evidence"),
)
RATING_VALUES = frozenset(value for value, _ in RATING_OPTIONS)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _direction(change: float | None) -> str:
    if change is None:
        return "insufficient history"
    if change > 1:
        return "up"
    if change < -1:
        return "down"
    return "flat"


def oil_readthrough(
    change: float | None, bullish_direction: str, subject: str = "contract odds"
) -> str:
    """Describe the oil implication of the move, not just the probability level."""
    direction = _direction(change)
    if direction == "insufficient history":
        return "Insufficient prior-day history for an oil read-through."
    if direction == "flat":
        return "No material day-over-day change; this contract is not adding a new oil impulse."
    descriptor = "Higher" if direction == "up" else "Lower"
    if (bullish_direction == "up" and direction == "up") or (
        bullish_direction == "down" and direction == "down"
    ):
        return f"{descriptor} {subject} are oil-bullish ({change:+.1f} pp vs prior day)."
    return f"{descriptor} {subject} are oil-bearish ({change:+.1f} pp vs prior day)."


def level_readthrough(current: float | None, bullish_direction: str) -> str:
    """Describe what the current level implies, separately from its change."""
    if current is None:
        return "Current probability unavailable."
    if current >= 70:
        level = "high"
    elif current >= 30:
        level = "intermediate"
    else:
        level = "low"
    if bullish_direction == "down":
        return (
            f"Current level is {current:.1f}%; this is an {level} normalization probability, implying an eventual "
            "oil-bearish normalization baseline."
        )
    return (
        f"Current level is {current:.1f}%; this is a {level} physical-risk probability, implying an "
        "oil-bullish risk baseline."
    )


def validate_rating(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if value not in RATING_VALUES:
        allowed = ", ".join(sorted(RATING_VALUES))
        raise ValueError(f"Unknown signal rating {value!r}; use one of: {allowed}")
    return value


def catalog_fingerprint(catalog: dict[str, Any]) -> str:
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_observation_record(
    *,
    as_of_et: str,
    signals: Iterable[dict[str, Any]],
    signal_level: str,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Create an append-only evidence record with blank user annotations."""
    normalized_signals = []
    for signal in signals:
        signal_scope = signal.get("signal_scope", "active_contract")
        normalized_signals.append(
            {
                "key": signal["key"],
                "event_id": signal.get("event_id"),
                "event_label": signal.get("event_label"),
                "contract_id": signal.get("contract_id"),
                "token_id": signal.get("token_id"),
                "header": signal["header"],
                "contract_label": signal.get("label"),
                "exact_question": signal.get("exact_question"),
                "signal_scope": signal_scope,
                "current_probability": _number(signal.get("current")),
                "prior_day_probability": _number(signal.get("prior_day")),
                "change_1d_pp": _number(signal.get("change_1d")),
                "change_7d_pp": _number(signal.get("change_7d")),
                "market_move": signal.get("market_move"),
                "bullish_direction": signal.get("bullish_direction"),
                "subject": signal.get("subject"),
                "direction_rationale": signal.get("direction_rationale"),
                "oil_readthrough": signal.get("oil_readthrough"),
                "level_readthrough": signal.get("level_readthrough"),
                "status": signal.get("status", "open"),
                "user_rating_vs_prior_day": None,
                "user_note": None,
            }
        )
    validate_exact_signal_rows(normalized_signals)
    record = {
        "schema_version": SIGNAL_REVIEW_SCHEMA_VERSION,
        "definition_version": SIGNAL_DEFINITION_VERSION,
        "catalog_fingerprint": catalog_fingerprint(catalog),
        "observation_id": as_of_et,
        "as_of_et": as_of_et,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "signal_level": signal_level,
        "signals": normalized_signals,
        "review_status": "unreviewed",
    }
    return record


def append_observation(path: str | Path, record: dict[str, Any]) -> bool:
    """Append once by observation ID; return whether a new line was written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("observation_id"):
                existing_ids.add(str(value["observation_id"]))
    observation_id = str(record["observation_id"])
    if observation_id in existing_ids:
        return False
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return True


def persist_observation(
    path: str | Path,
    *,
    as_of_et: str,
    signals: Iterable[dict[str, Any]],
    signal_level: str,
    catalog: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Build and persist one dashboard observation in one idempotent operation.

    The dashboard generator should call this function after collecting its
    source data.  It writes only the raw observation; user ratings and notes
    remain annotations that can be exported from the dashboard separately.
    """
    record = build_observation_record(
        as_of_et=as_of_et,
        signals=signals,
        signal_level=signal_level,
        catalog=catalog,
    )
    return record, append_observation(path, record)


def apply_user_review(
    record: dict[str, Any], ratings: dict[str, str], notes: dict[str, str] | None = None
) -> dict[str, Any]:
    """Return a reviewed copy without modifying the raw observation fields."""
    reviewed = json.loads(json.dumps(record))
    notes = notes or {}
    for signal in reviewed.get("signals", []):
        key = signal["key"]
        signal["user_rating_vs_prior_day"] = validate_rating(ratings.get(key))
        signal["user_note"] = notes.get(key) or None
    reviewed["review_status"] = "reviewed"
    return reviewed

