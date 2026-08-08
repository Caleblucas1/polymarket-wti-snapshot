"""Append-only probability forecasts for prediction-market review.

Market observations and independent forecasts are separate records. The market
probability is evidence; the independent probability, plausible range, confidence,
and catalysts are a forecaster annotation that can be scored after resolution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FORECAST_SCHEMA_VERSION = 2
CONFIDENCE_LEVELS = frozenset(
    {"low", "moderate_low", "moderate", "moderate_high", "high"}
)
FORECAST_STATUSES = frozenset({"active", "superseded", "resolved", "void"})


def _probability(value: Any, field_name: str) -> float:
    try:
        probability = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not 0.0 <= probability <= 100.0:
        raise ValueError(f"{field_name} must be between 0 and 100")
    return probability


def _clean_strings(values: Iterable[str] | None) -> list[str]:
    return [str(value).strip() for value in (values or ()) if str(value).strip()]


def forecast_id_for(
    *,
    as_of_et: str,
    forecaster: str,
    event_id: str,
    question: str,
    resolution_deadline: str,
    contract_id: str | None,
) -> str:
    """Return an exact-contract-safe forecast identity.

    Some event pages contain several dated contracts. When a condition ID has
    not yet been captured, deadline plus exact question prevents two contracts
    on the same event page from collapsing into one forecast identity.
    """
    contract_identity = (contract_id or "").strip()
    if not contract_identity:
        contract_identity = "|".join(
            [resolution_deadline.strip(), question.strip()]
        )
    canonical = "|".join(
        [as_of_et.strip(), forecaster.strip(), event_id.strip(), contract_identity]
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"forecast-{digest}"


def build_forecast_record(
    *,
    as_of_et: str,
    forecaster: str,
    event_id: str,
    question: str,
    market_probability: float,
    independent_probability: float,
    plausible_low: float,
    plausible_high: float,
    confidence_level: str,
    resolution_deadline: str,
    resolution_criteria: str,
    resolution_source: str,
    contract_id: str | None = None,
    source_url: str | None = None,
    market_probability_source: str = "observed_market",
    rationale: str = "",
    catalysts_raise_probability: Iterable[str] | None = None,
    catalysts_lower_probability: Iterable[str] | None = None,
    evidence_needed: Iterable[str] | None = None,
    status: str = "active",
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build one validated, scoreable probability forecast record."""
    market = _probability(market_probability, "market_probability")
    point = _probability(independent_probability, "independent_probability")
    low = _probability(plausible_low, "plausible_low")
    high = _probability(plausible_high, "plausible_high")

    if not low <= point <= high:
        raise ValueError(
            "plausible range must contain the independent point estimate: "
            "plausible_low <= independent_probability <= plausible_high"
        )
    if confidence_level not in CONFIDENCE_LEVELS:
        allowed = ", ".join(sorted(CONFIDENCE_LEVELS))
        raise ValueError(f"unknown confidence_level {confidence_level!r}; use one of: {allowed}")
    if status not in FORECAST_STATUSES:
        allowed = ", ".join(sorted(FORECAST_STATUSES))
        raise ValueError(f"unknown status {status!r}; use one of: {allowed}")
    for field_name, value in (
        ("as_of_et", as_of_et),
        ("forecaster", forecaster),
        ("event_id", event_id),
        ("question", question),
        ("resolution_deadline", resolution_deadline),
        ("resolution_criteria", resolution_criteria),
        ("resolution_source", resolution_source),
        ("market_probability_source", market_probability_source),
    ):
        if not str(value).strip():
            raise ValueError(f"{field_name} is required")

    record = {
        "schema_version": FORECAST_SCHEMA_VERSION,
        "forecast_id": forecast_id_for(
            as_of_et=as_of_et,
            forecaster=forecaster,
            event_id=event_id,
            question=question,
            resolution_deadline=resolution_deadline,
            contract_id=contract_id,
        ),
        "as_of_et": as_of_et,
        "created_at_utc": created_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "forecaster": forecaster,
        "event_id": event_id,
        "contract_id": contract_id,
        "question": question,
        "resolution_deadline": resolution_deadline,
        "resolution_criteria": resolution_criteria.strip(),
        "resolution_source": resolution_source.strip(),
        "source_url": source_url,
        "market_probability_source": market_probability_source,
        "market_probability": market,
        "independent_probability": point,
        "plausible_low": low,
        "plausible_high": high,
        "range_width_pp": round(high - low, 2),
        "confidence_level": confidence_level,
        "edge_pp": round(point - market, 2),
        "rationale": rationale.strip(),
        "catalysts_raise_probability": _clean_strings(catalysts_raise_probability),
        "catalysts_lower_probability": _clean_strings(catalysts_lower_probability),
        "evidence_needed": _clean_strings(evidence_needed),
        "status": status,
    }
    return record


def validate_forecast_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized copy or raise when a persisted record is malformed."""
    normalized = build_forecast_record(
        as_of_et=record["as_of_et"],
        forecaster=record["forecaster"],
        event_id=record["event_id"],
        contract_id=record.get("contract_id"),
        question=record["question"],
        resolution_deadline=record["resolution_deadline"],
        resolution_criteria=record["resolution_criteria"],
        resolution_source=record["resolution_source"],
        source_url=record.get("source_url"),
        market_probability_source=record.get(
            "market_probability_source", "observed_market"
        ),
        market_probability=record["market_probability"],
        independent_probability=record["independent_probability"],
        plausible_low=record["plausible_low"],
        plausible_high=record["plausible_high"],
        confidence_level=record["confidence_level"],
        rationale=record.get("rationale", ""),
        catalysts_raise_probability=record.get("catalysts_raise_probability"),
        catalysts_lower_probability=record.get("catalysts_lower_probability"),
        evidence_needed=record.get("evidence_needed"),
        status=record.get("status", "active"),
        created_at_utc=record.get("created_at_utc"),
    )
    if record.get("schema_version") != FORECAST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {record.get('schema_version')!r}; "
            f"expected {FORECAST_SCHEMA_VERSION}"
        )
    if record.get("forecast_id") != normalized["forecast_id"]:
        raise ValueError("forecast_id does not match the record identity fields")
    if round(float(record.get("edge_pp")), 2) != normalized["edge_pp"]:
        raise ValueError("edge_pp must equal independent_probability - market_probability")
    return normalized


def append_forecast(path: str | Path, record: dict[str, Any]) -> bool:
    """Append one validated record, duplicate-safe by forecast_id."""
    normalized = validate_forecast_record(record)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(existing, dict) and existing.get("forecast_id"):
                existing_ids.add(str(existing["forecast_id"]))
    if normalized["forecast_id"] in existing_ids:
        return False
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True) + "\n")
    return True
