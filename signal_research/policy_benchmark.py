from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_PROTOCOL_PATH = Path("signal_research/policy_historical_benchmark.json")
DEFAULT_CASES_PATH = Path("signal_records/policy_historical_cases.json")

BENCHMARK_ID = "POLICY-HISTORICAL-INTERPRETATION-001"
REGISTRY_ID = "POLICY-US-LEGISLATION-001"

ALLOWED_STAGES = {
    "selected",
    "packet_locked",
    "memo_sealed",
    "outcome_revealed",
    "scored",
    "retired",
}

STAGE_ORDER = {
    "selected": 0,
    "packet_locked": 1,
    "memo_sealed": 2,
    "outcome_revealed": 3,
    "scored": 4,
    "retired": 5,
}

REQUIRED_SELECTED_FIELDS = {
    "case_id",
    "stage",
    "law_name",
    "public_law_or_bill_identifier",
    "selection_locked_at_utc",
    "event_category",
    "case_type",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _substantive_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def payload_hash(payload: dict[str, Any], hash_field: str) -> str:
    canonical = {key: value for key, value in payload.items() if key != hash_field}
    return hashlib.sha256(_canonical_bytes(canonical)).hexdigest()


def load_protocol(path: str | Path = DEFAULT_PROTOCOL_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_case_registry(path: str | Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    return _read_json(path)


def interpretation_score(case: dict[str, Any], protocol: dict[str, Any]) -> float:
    return _score_family(case, protocol, "interpretation_accuracy")


def investment_score(case: dict[str, Any], protocol: dict[str, Any]) -> float:
    return _score_family(case, protocol, "investment_usefulness")


def _score_family(case: dict[str, Any], protocol: dict[str, Any], family: str) -> float:
    score_row = case.get("scores", {}).get(family, {})
    components = score_row.get("components", {})
    weights = protocol["scoring"][family]["component_weights"]
    if set(components) != set(weights):
        raise ValueError(f"{family} components do not match protocol weights")
    total = 0.0
    for name, maximum in weights.items():
        value = components[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{family}.{name} must be numeric")
        if value < 0 or value > maximum:
            raise ValueError(f"{family}.{name} must be between 0 and {maximum}")
        total += float(value)
    return total


def validate_protocol(path: str | Path = DEFAULT_PROTOCOL_PATH) -> list[str]:
    errors: list[str] = []
    protocol = load_protocol(path)

    if protocol.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"benchmark_id must be {BENCHMARK_ID}")
    if protocol.get("registry_id") != REGISTRY_ID:
        errors.append(f"registry_id must be {REGISTRY_ID}")
    if protocol.get("real_money_trading_authorized") is not False:
        errors.append("historical policy benchmark must prohibit real-money trading")
    if protocol.get("governing_principle") != "canonical_before_enhanced":
        errors.append("historical policy benchmark must declare canonical_before_enhanced")

    expected_phases = [
        "case_selection_locked",
        "point_in_time_packet_locked",
        "policy_impact_memo_sealed",
        "outcome_packet_revealed",
        "case_scored",
        "lessons_recorded",
    ]
    if protocol.get("phase_order") != expected_phases:
        errors.append("phase_order must preserve selection, packet, memo, reveal, score and lessons order")

    firewall = protocol.get("temporal_firewall")
    if not isinstance(firewall, dict):
        errors.append("temporal_firewall must be an object")
    else:
        for key in (
            "information_cutoff_required",
            "pre_cutoff_sources_only_in_input_packet",
            "post_cutoff_news_prohibited_before_memo_seal",
            "post_event_prices_prohibited_before_memo_seal",
            "memo_hash_required_before_outcome_reveal",
        ):
            if firewall.get(key) is not True:
                errors.append(f"temporal_firewall.{key} must be true")

    scoring = protocol.get("scoring")
    if not isinstance(scoring, dict):
        errors.append("scoring must be an object")
    else:
        for family in ("interpretation_accuracy", "investment_usefulness"):
            weights = scoring.get(family, {}).get("component_weights")
            if not isinstance(weights, dict) or not weights:
                errors.append(f"scoring.{family}.component_weights must be nonempty")
            elif sum(weights.values()) != 100:
                errors.append(f"scoring.{family} component weights must sum to 100")
        if scoring.get("scores_must_remain_separate") is not True:
            errors.append("interpretation and investment scores must remain separate")
        if scoring.get("no_capital_rights_from_single_case") is not True:
            errors.append("a single case must not grant capital rights")

    prohibited = " ".join(protocol.get("prohibited_practices", [])).lower()
    for required_phrase in (
        "do not select cases because the subsequent winner is already known",
        "do not use post-event prices",
        "do not treat correct legal interpretation as proof of trading alpha",
        "do not authorize real-money trading",
    ):
        if required_phrase not in prohibited:
            errors.append(f"prohibited_practices must include: {required_phrase}")

    return errors


def validate_cases(
    cases_path: str | Path = DEFAULT_CASES_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> list[str]:
    errors: list[str] = []
    protocol = load_protocol(protocol_path)
    registry = load_case_registry(cases_path)

    if registry.get("benchmark_id") != BENCHMARK_ID:
        errors.append(f"case registry benchmark_id must be {BENCHMARK_ID}")
    if registry.get("registry_id") != REGISTRY_ID:
        errors.append(f"case registry registry_id must be {REGISTRY_ID}")
    if registry.get("real_money_trading_authorized") is not False:
        errors.append("case registry must prohibit real-money trading")

    cases = registry.get("cases")
    if not isinstance(cases, list):
        return errors + ["case registry cases must be a list"]
    if not all(isinstance(case, dict) for case in cases):
        return errors + ["every historical policy case must be an object"]

    seen_ids: set[str] = set()
    required_input = set(protocol.get("required_input_packet_fields", []))
    required_memo = set(protocol.get("required_sealed_memo_fields", []))
    required_outcome = set(protocol.get("required_outcome_packet_fields", []))

    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"
        missing_selected = sorted(REQUIRED_SELECTED_FIELDS - set(case))
        if missing_selected:
            errors.append(f"{prefix}: missing selected fields {missing_selected}")

        case_id = case.get("case_id")
        if not _substantive_text(case_id):
            errors.append(f"{prefix}: case_id must be substantive text")
        elif case_id in seen_ids:
            errors.append(f"duplicate case_id {case_id}")
        else:
            seen_ids.add(case_id)

        stage = case.get("stage")
        if stage not in ALLOWED_STAGES:
            errors.append(f"{prefix}: invalid stage {stage!r}")
            continue

        if case.get("registry_id", REGISTRY_ID) != REGISTRY_ID:
            errors.append(f"{prefix}: registry_id must be {REGISTRY_ID}")
        if case.get("real_money_trading_authorized", False) is not False:
            errors.append(f"{prefix}: real-money trading must remain unauthorized")

        rank = STAGE_ORDER[stage]
        input_packet = case.get("input_packet")
        memo = case.get("sealed_memo")
        outcome = case.get("outcome_packet")
        scores = case.get("scores")

        if rank >= STAGE_ORDER["packet_locked"] and stage != "retired":
            errors.extend(
                _validate_hashed_packet(prefix, "input_packet", input_packet, required_input, "input_packet_hash")
            )
        elif input_packet is not None and not isinstance(input_packet, dict):
            errors.append(f"{prefix}: input_packet must be an object when present")

        if rank >= STAGE_ORDER["memo_sealed"] and stage != "retired":
            errors.extend(
                _validate_hashed_packet(prefix, "sealed_memo", memo, required_memo, "memo_hash")
            )
        elif memo is not None and not isinstance(memo, dict):
            errors.append(f"{prefix}: sealed_memo must be an object when present")

        if rank < STAGE_ORDER["outcome_revealed"]:
            if outcome is not None:
                errors.append(f"{prefix}: outcome_packet is prohibited before outcome_revealed")
            if scores is not None:
                errors.append(f"{prefix}: scores are prohibited before outcome_revealed")
        elif stage != "retired":
            errors.extend(
                _validate_hashed_packet(prefix, "outcome_packet", outcome, required_outcome, "outcome_packet_hash")
            )

        if stage == "scored":
            if not isinstance(scores, dict):
                errors.append(f"{prefix}: scored cases require scores")
            else:
                try:
                    interpreted = interpretation_score(case, protocol)
                    invested = investment_score(case, protocol)
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(f"{prefix}: invalid scores: {exc}")
                else:
                    if scores.get("interpretation_accuracy", {}).get("total") != interpreted:
                        errors.append(f"{prefix}: interpretation total must equal component sum")
                    if scores.get("investment_usefulness", {}).get("total") != invested:
                        errors.append(f"{prefix}: investment total must equal component sum")
                    if not _substantive_text(scores.get("attribution_review")):
                        errors.append(f"{prefix}: scored cases require an attribution_review")

    return errors


def _validate_hashed_packet(
    prefix: str,
    name: str,
    value: object,
    required_fields: set[str],
    hash_field: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"{prefix}: {name} must be an object"]
    missing = sorted(required_fields - set(value))
    if missing:
        errors.append(f"{prefix}: {name} missing fields {missing}")
    expected = value.get(hash_field)
    if not _substantive_text(expected):
        errors.append(f"{prefix}: {name}.{hash_field} must be present")
    elif expected != payload_hash(value, hash_field):
        errors.append(f"{prefix}: {name}.{hash_field} does not match payload")
    return errors


def validate_benchmark(
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
    cases_path: str | Path = DEFAULT_CASES_PATH,
) -> list[str]:
    return [
        *(f"protocol: {error}" for error in validate_protocol(protocol_path)),
        *(f"cases: {error}" for error in validate_cases(cases_path, protocol_path)),
    ]


def summarize_benchmark(
    cases_path: str | Path = DEFAULT_CASES_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> dict[str, Any]:
    registry = load_case_registry(cases_path)
    protocol = load_protocol(protocol_path)
    cases = registry.get("cases", [])
    stage_counts = Counter(case.get("stage", "invalid") for case in cases if isinstance(case, dict))
    scored = [case for case in cases if isinstance(case, dict) and case.get("stage") == "scored"]
    interpretation_scores = [interpretation_score(case, protocol) for case in scored]
    investment_scores = [investment_score(case, protocol) for case in scored]
    return {
        "benchmark_id": BENCHMARK_ID,
        "registry_id": REGISTRY_ID,
        "status": protocol.get("status"),
        "cases": len(cases),
        "stage_counts": dict(sorted(stage_counts.items())),
        "scored_cases": len(scored),
        "mean_interpretation_accuracy": (
            sum(interpretation_scores) / len(interpretation_scores) if interpretation_scores else None
        ),
        "mean_investment_usefulness": (
            sum(investment_scores) / len(investment_scores) if investment_scores else None
        ),
        "scores_kept_separate": True,
        "real_money_trading_authorized": False,
        "valid": not validate_benchmark(protocol_path, cases_path),
    }


def get_case(case_id: str, cases_path: str | Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    registry = load_case_registry(cases_path)
    for case in registry.get("cases", []):
        if isinstance(case, dict) and case.get("case_id") == case_id:
            return dict(case)
    raise KeyError(f"unknown policy benchmark case: {case_id}")
