from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_research.policy_benchmark import (
    interpretation_score,
    load_case_registry,
    load_protocol,
    validate_benchmark,
)


DEFAULT_ROADMAP_PATH = Path("signal_research/policy_roadmap.json")
DEFAULT_REVISIONS_PATH = Path("signal_records/policy_framework_revisions.json")
DEFAULT_PROSPECTIVE_PATH = Path("signal_records/policy_prospective_cases.json")

ROADMAP_ID = "POLICY-ROADMAP-001"
REGISTRY_ID = "POLICY-US-LEGISLATION-001"
EXPECTED_KEYS = [
    "freeze_post_passage_rule",
    "build_diverse_historical_legislation_set",
    "reconstruct_point_in_time_cases",
    "generate_and_seal_blinded_impact_memos",
    "reveal_outcomes_and_explanatory_reporting",
    "score_interpretation_and_investment_separately",
    "improve_framework_from_errors",
    "begin_untouched_prospective_post_passage_testing",
]
ALLOWED_STATUSES = {
    "completed",
    "ready_to_start",
    "in_progress",
    "blocked_by_dependency",
    "blocked_by_readiness_gate",
}


def _read(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_roadmap(path: str | Path = DEFAULT_ROADMAP_PATH) -> dict[str, Any]:
    return _read(path)


def load_revisions(path: str | Path = DEFAULT_REVISIONS_PATH) -> dict[str, Any]:
    return _read(path)


def load_prospective(path: str | Path = DEFAULT_PROSPECTIVE_PATH) -> dict[str, Any]:
    return _read(path)


def historical_readiness(
    roadmap_path: str | Path = DEFAULT_ROADMAP_PATH,
    cases_path: str | Path = "signal_records/policy_historical_cases.json",
    protocol_path: str | Path = "signal_research/policy_historical_benchmark.json",
) -> dict[str, Any]:
    roadmap = load_roadmap(roadmap_path)
    gate = roadmap["historical_readiness_gate"]
    registry = load_case_registry(cases_path)
    protocol = load_protocol(protocol_path)
    cases = [case for case in registry.get("cases", []) if isinstance(case, dict)]
    selected = len(cases)
    scored = [case for case in cases if case.get("stage") == "scored"]
    categories = {str(case.get("event_category")) for case in cases}
    case_types = {str(case.get("case_type")) for case in cases}
    scores: list[float] = []
    for case in scored:
        try:
            scores.append(interpretation_score(case, protocol))
        except (KeyError, TypeError, ValueError):
            pass
    mean_interpretation = sum(scores) / len(scores) if scores else None
    failures: list[str] = []
    if selected < gate["minimum_selected_cases"]:
        failures.append("minimum_selected_cases")
    if len(scored) < gate["minimum_scored_cases"]:
        failures.append("minimum_scored_cases")
    if not set(gate["required_event_categories"]).issubset(categories):
        failures.append("required_event_categories")
    if not set(gate["required_case_types"]).issubset(case_types):
        failures.append("required_case_types")
    if mean_interpretation is None or mean_interpretation < gate["minimum_mean_interpretation_accuracy"]:
        failures.append("minimum_mean_interpretation_accuracy")
    benchmark_errors = validate_benchmark(protocol_path, cases_path)
    if benchmark_errors:
        failures.append("historical_benchmark_validation")
    return {
        "passed": not failures,
        "failures": failures,
        "selected_cases": selected,
        "scored_cases": len(scored),
        "mean_interpretation_accuracy": mean_interpretation,
        "covered_event_categories": sorted(categories),
        "covered_case_types": sorted(case_types),
        "benchmark_errors": benchmark_errors,
        "capital_right_after_pass": "research_only",
        "real_money_trading_authorized": False,
    }


def validate_roadmap(
    roadmap_path: str | Path = DEFAULT_ROADMAP_PATH,
    revisions_path: str | Path = DEFAULT_REVISIONS_PATH,
    prospective_path: str | Path = DEFAULT_PROSPECTIVE_PATH,
    cases_path: str | Path = "signal_records/policy_historical_cases.json",
    protocol_path: str | Path = "signal_research/policy_historical_benchmark.json",
) -> list[str]:
    errors: list[str] = []
    roadmap = load_roadmap(roadmap_path)
    if roadmap.get("roadmap_id") != ROADMAP_ID:
        errors.append(f"roadmap_id must be {ROADMAP_ID}")
    if roadmap.get("registry_id") != REGISTRY_ID:
        errors.append(f"registry_id must be {REGISTRY_ID}")
    if roadmap.get("governing_principle") != "canonical_before_enhanced":
        errors.append("roadmap must declare canonical_before_enhanced")
    if roadmap.get("real_money_trading_authorized") is not False:
        errors.append("roadmap must prohibit real-money trading")

    steps = roadmap.get("steps")
    if not isinstance(steps, list) or len(steps) != 8:
        errors.append("roadmap must contain exactly eight steps")
        steps = []
    else:
        if [step.get("step") for step in steps] != list(range(1, 9)):
            errors.append("roadmap steps must be numbered 1 through 8")
        if [step.get("key") for step in steps] != EXPECTED_KEYS:
            errors.append("roadmap step keys or order do not match the approved roadmap")
        for step in steps:
            number = step.get("step")
            if step.get("status") not in ALLOWED_STATUSES:
                errors.append(f"step {number}: invalid status")
            dependencies = step.get("dependencies")
            if not isinstance(dependencies, list) or any(
                not isinstance(dep, int) or dep >= number for dep in dependencies
            ):
                errors.append(f"step {number}: dependencies must reference earlier steps")
            if not step.get("completion_criteria"):
                errors.append(f"step {number}: completion criteria are required")
            if not step.get("artifacts"):
                errors.append(f"step {number}: artifacts are required")

    change_control = roadmap.get("change_control", {})
    for key in (
        "roadmap_changes_require_version_bump",
        "threshold_changes_after_case_selection_are_prohibited",
        "historical_results_must_not_be_rewritten",
        "framework_revisions_apply_prospectively",
    ):
        if change_control.get(key) is not True:
            errors.append(f"change_control.{key} must be true")

    revisions = load_revisions(revisions_path)
    if revisions.get("real_money_trading_authorized") is not False:
        errors.append("framework revisions must prohibit real-money trading")
    taxonomy = set(revisions.get("error_taxonomy", []))
    seen_revisions: set[str] = set()
    for index, record in enumerate(revisions.get("records", [])):
        rid = record.get("revision_id")
        if not isinstance(rid, str) or not rid:
            errors.append(f"revisions[{index}]: revision_id is required")
        elif rid in seen_revisions:
            errors.append(f"duplicate revision_id {rid}")
        else:
            seen_revisions.add(rid)
        if record.get("error_taxonomy") not in taxonomy:
            errors.append(f"revisions[{index}]: unknown error taxonomy")
        if record.get("applies_prospectively_only") is not True:
            errors.append(f"revisions[{index}]: must apply prospectively only")
        if record.get("original_results_preserved") is not True:
            errors.append(f"revisions[{index}]: must preserve original results")
        if not record.get("source_case_ids"):
            errors.append(f"revisions[{index}]: source_case_ids are required")

    prospective = load_prospective(prospective_path)
    if prospective.get("real_money_trading_authorized") is not False:
        errors.append("prospective registry must prohibit real-money trading")
    readiness = historical_readiness(roadmap_path, cases_path, protocol_path)
    prospective_cases = prospective.get("cases")
    if not isinstance(prospective_cases, list):
        errors.append("prospective cases must be a list")
        prospective_cases = []
    if prospective_cases and not readiness["passed"]:
        errors.append("prospective cases cannot begin before the historical readiness gate passes")
    if readiness["passed"] and not prospective.get("activation_timestamp_utc"):
        errors.append("prospective activation timestamp is required after readiness passes")
    for index, case in enumerate(prospective_cases):
        if not isinstance(case, dict):
            errors.append(f"prospective[{index}] must be an object")
            continue
        for field in (
            "case_id",
            "first_observed_at_utc",
            "information_cutoff_utc",
            "public_law_or_bill_identifier",
            "memo_hash",
        ):
            if not case.get(field):
                errors.append(f"prospective[{index}]: {field} is required")
        if case.get("real_money_trading_authorized", False) is not False:
            errors.append(f"prospective[{index}]: real-money trading must remain unauthorized")

    return errors


def summarize_roadmap(
    roadmap_path: str | Path = DEFAULT_ROADMAP_PATH,
    revisions_path: str | Path = DEFAULT_REVISIONS_PATH,
    prospective_path: str | Path = DEFAULT_PROSPECTIVE_PATH,
) -> dict[str, Any]:
    roadmap = load_roadmap(roadmap_path)
    revisions = load_revisions(revisions_path)
    prospective = load_prospective(prospective_path)
    readiness = historical_readiness(roadmap_path)
    return {
        "roadmap_id": roadmap["roadmap_id"],
        "registry_id": roadmap["registry_id"],
        "steps": [
            {
                "step": step["step"],
                "key": step["key"],
                "status": step["status"],
                "dependencies": step["dependencies"],
            }
            for step in roadmap["steps"]
        ],
        "historical_readiness_gate": readiness,
        "framework_revisions": len(revisions.get("records", [])),
        "prospective_status": prospective.get("status"),
        "prospective_cases": len(prospective.get("cases", [])),
        "valid": not validate_roadmap(),
        "real_money_trading_authorized": False,
    }
