from __future__ import annotations

import copy
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from signal_research.policy_benchmark import (
    interpretation_score,
    investment_score,
    load_protocol,
    validate_cases,
)


DEFAULT_PILOTS_PATH = Path("signal_records/policy_case_pilots.json")
DEFAULT_OUTCOMES_PATH = Path("signal_records/policy_case_pilot_outcomes.json")
DEFAULT_PROTOCOL_PATH = Path("signal_research/policy_historical_benchmark.json")

PILOT_REGISTRY_ID = "POLICY-CASE-PILOTS-001"
BENCHMARK_ID = "POLICY-HISTORICAL-INTERPRETATION-001"
REGISTRY_ID = "POLICY-US-LEGISLATION-001"


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_pilots(path: str | Path = DEFAULT_PILOTS_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_outcomes(path: str | Path = DEFAULT_OUTCOMES_PATH) -> dict[str, Any]:
    return _read_json(path)


def combined_cases(
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
    outcomes_path: str | Path = DEFAULT_OUTCOMES_PATH,
) -> list[dict[str, Any]]:
    registry = load_pilots(pilots_path)
    outcomes = load_outcomes(outcomes_path)
    outcome_by_id = {
        row.get("case_id"): row
        for row in outcomes.get("outcomes", [])
        if isinstance(row, dict) and isinstance(row.get("case_id"), str)
    }
    combined: list[dict[str, Any]] = []
    for source_case in registry.get("cases", []):
        if not isinstance(source_case, dict):
            continue
        case = copy.deepcopy(source_case)
        reveal = outcome_by_id.get(case.get("case_id"))
        if reveal is not None:
            case["stage"] = reveal.get("revealed_stage")
            for field in ("outcome_packet", "scores", "lessons", "pipeline_result"):
                if field in reveal:
                    case[field] = copy.deepcopy(reveal[field])
        combined.append(case)
    return combined


def _validate_registry_identity(registry: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append(f"{label} schema_version must be 1")
    if registry.get("pilot_registry_id") != PILOT_REGISTRY_ID:
        errors.append(f"{label} pilot_registry_id must be {PILOT_REGISTRY_ID}")
    if registry.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"{label} benchmark_id must be {BENCHMARK_ID}")
    if registry.get("registry_id") != REGISTRY_ID:
        errors.append(f"{label} registry_id must be {REGISTRY_ID}")
    if registry.get("readiness_eligible") is not False:
        errors.append(f"{label} must remain ineligible for readiness counts")
    if registry.get("real_money_trading_authorized") is not False:
        errors.append(f"{label} must prohibit real-money trading")
    return errors


def validate_pilots(
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
    outcomes_path: str | Path = DEFAULT_OUTCOMES_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> list[str]:
    errors: list[str] = []
    registry = load_pilots(pilots_path)
    outcomes = load_outcomes(outcomes_path)
    errors.extend(_validate_registry_identity(registry, "pilot registry"))
    errors.extend(_validate_registry_identity(outcomes, "pilot outcome registry"))

    cases = registry.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("pilot registry must contain at least one pilot case")
        cases = []
    outcome_rows = outcomes.get("outcomes")
    if not isinstance(outcome_rows, list):
        errors.append("pilot outcome registry outcomes must be a list")
        outcome_rows = []

    seen_ids: set[str] = set()
    base_ids: set[str] = set()
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
            base_ids.add(case_id)
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

    seen_outcomes: set[str] = set()
    for index, row in enumerate(outcome_rows):
        prefix = f"outcomes[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}: outcome must be an object")
            continue
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{prefix}: case_id is required")
            continue
        if case_id in seen_outcomes:
            errors.append(f"duplicate pilot outcome case_id {case_id}")
        seen_outcomes.add(case_id)
        if case_id not in base_ids:
            errors.append(f"{prefix}: outcome references unknown pilot {case_id}")
        if row.get("revealed_stage") not in {"outcome_revealed", "scored"}:
            errors.append(f"{prefix}: revealed_stage must be outcome_revealed or scored")
        if row.get("readiness_eligible") is not False:
            errors.append(f"{prefix}: readiness_eligible must be false")
        if row.get("known_outcome_contamination") is not True:
            errors.append(f"{prefix}: known_outcome_contamination must be true")
        pipeline = row.get("pipeline_result")
        if not isinstance(pipeline, dict):
            errors.append(f"{prefix}: pipeline_result must be an object")
        else:
            if pipeline.get("readiness_credit") != 0:
                errors.append(f"{prefix}: readiness_credit must be zero")
            if pipeline.get("capital_rights_change") != "none":
                errors.append(f"{prefix}: capital_rights_change must be none")
            if pipeline.get("real_money_trading_authorized") is not False:
                errors.append(f"{prefix}: real-money trading must remain unauthorized")

    merged = combined_cases(pilots_path, outcomes_path)
    temporary_registry = {
        "schema_version": 3,
        "benchmark_id": BENCHMARK_ID,
        "registry_id": REGISTRY_ID,
        "status": "retrospective_pipeline_pilots",
        "real_money_trading_authorized": False,
        "cases": merged,
    }
    with tempfile.TemporaryDirectory() as directory:
        merged_path = Path(directory) / "merged_pilots.json"
        merged_path.write_text(json.dumps(temporary_registry), encoding="utf-8")
        errors.extend(
            f"benchmark_schema: {error}"
            for error in validate_cases(merged_path, protocol_path)
        )
    return errors


def get_pilot(
    case_id: str,
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
    outcomes_path: str | Path = DEFAULT_OUTCOMES_PATH,
) -> dict[str, Any]:
    for case in combined_cases(pilots_path, outcomes_path):
        if case.get("case_id") == case_id:
            return case
    raise KeyError(f"unknown policy pilot case: {case_id}")


def summarize_pilots(
    pilots_path: str | Path = DEFAULT_PILOTS_PATH,
    outcomes_path: str | Path = DEFAULT_OUTCOMES_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    cases = combined_cases(pilots_path, outcomes_path)
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
        "canonical_trade_results": Counter(
            str(case.get("pipeline_result", {}).get("canonical_trade_result", "not_revealed"))
            for case in cases
        ),
        "real_money_trading_authorized": False,
        "valid": not validate_pilots(pilots_path, outcomes_path, protocol_path),
    }
