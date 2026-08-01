from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from signal_research.policy_benchmark import (
    get_case as get_benchmark_case,
    interpretation_score,
    investment_score,
    load_protocol,
    validate_cases,
)


DEFAULT_PILOTS_PATH = Path("signal_records/policy_case_pilots.json")
DEFAULT_PROTOCOL_PATH = Path("signal_research/policy_historical_benchmark.json")

PILOT_REGISTRY_ID = "POLICY-CASE-PILOTS-001"
BENCHMARK_ID = "POLICY-HISTORICAL-INTERPRETATION-001"
REGISTRY_ID = "POLICY-US-LEGISLATION-001"


def load_pilots(path: str | Path = DEFAULT_PILOTS_PATH) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_pilots(
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> list[str]:
    errors: list[str] = []
    registry = load_pilots(pilots_path)

    if registry.get("schema_version") != 1:
        errors.append("pilot registry schema_version must be 1")
    if registry.get("pilot_registry_id") != PILOT_REGISTRY_ID:
        errors.append(f"pilot_registry_id must be {PILOT_REGISTRY_ID}")
    if registry.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"benchmark_id must be {BENCHMARK_ID}")
    if registry.get("registry_id") != REGISTRY_ID:
        errors.append(f"registry_id must be {REGISTRY_ID}")
    if registry.get("readiness_eligible") is not False:
        errors.append("the policy pilot registry must remain ineligible for readiness counts")
    if registry.get("real_money_trading_authorized") is not False:
        errors.append("policy pilots must prohibit real-money trading")

    cases = registry.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("pilot registry must contain at least one pilot case")
        cases = []

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"pilots[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix}: pilot case must be an object")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{prefix}: case_id is required")
        elif case_id in seen_ids:
            errors.append(f"duplicate pilot case_id {case_id}")
        else:
            seen_ids.add(case_id)
        if case.get("benchmark_role") != "retrospective_pipeline_pilot":
            errors.append(f"{prefix}: benchmark_role must be retrospective_pipeline_pilot")
        if case.get("readiness_eligible") is not False:
            errors.append(f"{prefix}: readiness_eligible must be false")
        if case.get("known_outcome_contamination") is not True:
            errors.append(f"{prefix}: known_outcome_contamination must be true")
        if not isinstance(case.get("pilot_reason"), str) or not case["pilot_reason"].strip():
            errors.append(f"{prefix}: pilot_reason is required")
        if case.get("real_money_trading_authorized") is not False:
            errors.append(f"{prefix}: real-money trading must remain unauthorized")

    errors.extend(f"benchmark_schema: {error}" for error in validate_cases(pilots_path, protocol_path))
    return errors


def get_pilot(
    case_id: str,
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
) -> dict[str, Any]:
    registry = load_pilots(pilots_path)
    for case in registry.get("cases", []):
        if isinstance(case, dict) and case.get("case_id") == case_id:
            return dict(case)
    raise KeyError(f"unknown policy pilot case: {case_id}")


def summarize_pilots(
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, Any]:
    registry = load_pilots(pilots_path)
    protocol = load_protocol(protocol_path)
    cases = [case for case in registry.get("cases", []) if isinstance(case, dict)]
    stage_counts = Counter(str(case.get("stage", "invalid")) for case in cases)
    scored = [case for case in cases if case.get("stage") == "scored"]

    interpretation_scores: list[float] = []
    investment_scores: list[float] = []
    for case in scored:
        try:
            interpretation_scores.append(interpretation_score(case, protocol))
            investment_scores.append(investment_score(case, protocol))
        except (KeyError, TypeError, ValueError):
            continue

    return {
        "pilot_registry_id": PILOT_REGISTRY_ID,
        "benchmark_id": BENCHMARK_ID,
        "registry_id": REGISTRY_ID,
        "cases": len(cases),
        "stage_counts": dict(sorted(stage_counts.items())),
        "scored_cases": len(scored),
        "mean_interpretation_accuracy": (
            sum(interpretation_scores) / len(interpretation_scores)
            if interpretation_scores
            else None
        ),
        "mean_investment_usefulness": (
            sum(investment_scores) / len(investment_scores)
            if investment_scores
            else None
        ),
        "readiness_eligible_cases": 0,
        "readiness_eligible": False,
        "known_outcome_contamination_disclosed": all(
            case.get("known_outcome_contamination") is True for case in cases
        ),
        "real_money_trading_authorized": False,
        "valid": not validate_pilots(pilots_path, protocol_path),
    }
