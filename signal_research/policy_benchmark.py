from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
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


def _parse_timestamp(value: object) -> datetime | None:
    if not _substantive_text(value):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


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

    if protocol.get("schema_version") != 2:
        errors.append("historical policy benchmark schema_version must be 2")
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
            "source_stance_tagging_required",
            "contradictory_evidence_review_required",
        ):
            if firewall.get(key) is not True:
                errors.append(f"temporal_firewall.{key} must be true")

    evidence_schema = protocol.get("evidence_record_schema")
    if not isinstance(evidence_schema, dict):
        errors.append("evidence_record_schema must be an object")
    else:
        required_evidence_fields = {
            "evidence_id",
            "source_url",
            "title",
            "publisher",
            "published_at_utc",
            "accessed_at_utc",
            "source_type",
            "evidence_stance",
            "affected_claims",
            "temporal_role",
            "available_before_memo_seal",
            "reliability",
            "summary",
            "archive_reference",
            "notes",
        }
        configured = set(evidence_schema.get("required_fields", []))
        if configured != required_evidence_fields:
            errors.append("evidence_record_schema.required_fields must match the source-level audit schema")
        for key in (
            "allowed_stances",
            "allowed_temporal_roles",
            "allowed_source_types",
            "allowed_reliability",
        ):
            values = evidence_schema.get(key)
            if not isinstance(values, list) or not values or not all(_substantive_text(item) for item in values):
                errors.append(f"evidence_record_schema.{key} must be a nonempty text list")
        if set(evidence_schema.get("allowed_stances", [])) != {
            "supports",
            "contradicts",
            "mixed",
            "neutral_context",
        }:
            errors.append("allowed_stances must include supports, contradicts, mixed and neutral_context")

    required_review_fields = set(protocol.get("required_contradictory_evidence_review_fields", []))
    if required_review_fields != {
        "review_completed_at_utc",
        "search_scope",
        "contradictory_evidence_ids",
        "mixed_evidence_ids",
        "late_discovered_pre_cutoff_evidence_ids",
        "no_contradictory_evidence_found",
        "reviewer_notes",
    }:
        errors.append("required_contradictory_evidence_review_fields must match the contradiction-review schema")

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
        "do not omit, downgrade or bury contradictory evidence",
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
            seen_ids.add(str(case_id))

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
        evidence_by_id: dict[str, dict[str, Any]] = {}

        if rank >= STAGE_ORDER["packet_locked"] and stage != "retired":
            errors.extend(
                _validate_hashed_packet(
                    prefix,
                    "input_packet",
                    input_packet,
                    required_input,
                    "input_packet_hash",
                )
            )
            if isinstance(input_packet, dict):
                input_evidence, evidence_errors = _validate_evidence_records(
                    f"{prefix}.input_packet",
                    input_packet.get("pre_cutoff_evidence_records"),
                    protocol,
                    expected_temporal_role="pre_cutoff_input",
                    cutoff_timestamp=input_packet.get("information_cutoff_utc"),
                    require_official_text=True,
                )
                errors.extend(evidence_errors)
                evidence_by_id.update(input_evidence)
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
                _validate_hashed_packet(
                    prefix,
                    "outcome_packet",
                    outcome,
                    required_outcome,
                    "outcome_packet_hash",
                )
            )
            if isinstance(outcome, dict):
                outcome_evidence, evidence_errors = _validate_evidence_records(
                    f"{prefix}.outcome_packet",
                    outcome.get("post_outcome_evidence_records"),
                    protocol,
                    expected_temporal_role="post_outcome_reveal",
                    cutoff_timestamp=outcome.get("outcome_revealed_at_utc"),
                    require_official_text=False,
                )
                errors.extend(evidence_errors)
                duplicate_ids = sorted(set(evidence_by_id).intersection(outcome_evidence))
                for evidence_id in duplicate_ids:
                    errors.append(f"{prefix}: duplicate evidence_id across packets: {evidence_id}")
                evidence_by_id.update(outcome_evidence)
                errors.extend(
                    _validate_contradictory_evidence_review(
                        f"{prefix}.outcome_packet",
                        outcome.get("contradictory_evidence_review"),
                        protocol,
                        evidence_by_id,
                        set(outcome_evidence),
                    )
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


def _validate_evidence_records(
    prefix: str,
    records: object,
    protocol: dict[str, Any],
    *,
    expected_temporal_role: str,
    cutoff_timestamp: object,
    require_official_text: bool,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(records, list):
        return by_id, [f"{prefix}: evidence records must be a list"]

    schema = protocol.get("evidence_record_schema", {})
    required = set(schema.get("required_fields", []))
    allowed_stances = set(schema.get("allowed_stances", []))
    allowed_roles = set(schema.get("allowed_temporal_roles", []))
    allowed_types = set(schema.get("allowed_source_types", []))
    allowed_reliability = set(schema.get("allowed_reliability", []))
    cutoff = _parse_timestamp(cutoff_timestamp)
    if cutoff is None:
        errors.append(f"{prefix}: evidence cutoff timestamp must be a timezone-aware ISO timestamp")

    official_text_found = False
    for index, record in enumerate(records):
        record_prefix = f"{prefix}.evidence[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{record_prefix}: evidence record must be an object")
            continue
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"{record_prefix}: missing fields {missing}")

        evidence_id = record.get("evidence_id")
        if not _substantive_text(evidence_id):
            errors.append(f"{record_prefix}: evidence_id must be substantive text")
        elif evidence_id in by_id:
            errors.append(f"{record_prefix}: duplicate evidence_id {evidence_id}")
        else:
            by_id[str(evidence_id)] = record

        for field in (
            "source_url",
            "title",
            "publisher",
            "summary",
            "archive_reference",
        ):
            if not _substantive_text(record.get(field)):
                errors.append(f"{record_prefix}: {field} must be substantive text")
        if not isinstance(record.get("notes"), str):
            errors.append(f"{record_prefix}: notes must be text")

        stance = record.get("evidence_stance")
        if stance not in allowed_stances:
            errors.append(f"{record_prefix}: invalid evidence_stance {stance!r}")

        source_type = record.get("source_type")
        if source_type not in allowed_types:
            errors.append(f"{record_prefix}: invalid source_type {source_type!r}")
        if source_type == "official_text":
            official_text_found = True

        role = record.get("temporal_role")
        if role not in allowed_roles:
            errors.append(f"{record_prefix}: invalid temporal_role {role!r}")
        elif role != expected_temporal_role:
            errors.append(f"{record_prefix}: temporal_role must be {expected_temporal_role}")

        reliability = record.get("reliability")
        if reliability not in allowed_reliability:
            errors.append(f"{record_prefix}: invalid reliability {reliability!r}")

        affected_claims = record.get("affected_claims")
        if not isinstance(affected_claims, list) or not all(
            _substantive_text(item) for item in affected_claims
        ):
            errors.append(f"{record_prefix}: affected_claims must be a text list")
        elif stance in {"supports", "contradicts", "mixed"} and not affected_claims:
            errors.append(f"{record_prefix}: {stance} evidence must identify affected_claims")

        published = _parse_timestamp(record.get("published_at_utc"))
        accessed = _parse_timestamp(record.get("accessed_at_utc"))
        if published is None:
            errors.append(f"{record_prefix}: published_at_utc must be timezone-aware ISO")
        if accessed is None:
            errors.append(f"{record_prefix}: accessed_at_utc must be timezone-aware ISO")
        if published is not None and accessed is not None and accessed < published:
            errors.append(f"{record_prefix}: accessed_at_utc cannot precede publication")
        if published is not None and cutoff is not None and published > cutoff:
            errors.append(f"{record_prefix}: evidence was published after its packet cutoff")

        available_before_memo = record.get("available_before_memo_seal")
        if not isinstance(available_before_memo, bool):
            errors.append(f"{record_prefix}: available_before_memo_seal must be boolean")
        elif expected_temporal_role == "pre_cutoff_input" and not available_before_memo:
            errors.append(
                f"{record_prefix}: pre-cutoff evidence must have been available before memo seal"
            )

    if require_official_text and records and not official_text_found:
        errors.append(f"{prefix}: at least one official_text evidence record is required")
    return by_id, errors


def _validate_contradictory_evidence_review(
    prefix: str,
    review: object,
    protocol: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    outcome_evidence_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(review, dict):
        return [f"{prefix}: contradictory_evidence_review must be an object"]

    required = set(protocol.get("required_contradictory_evidence_review_fields", []))
    missing = sorted(required - set(review))
    if missing:
        errors.append(f"{prefix}: contradictory_evidence_review missing fields {missing}")

    reviewed_at = _parse_timestamp(review.get("review_completed_at_utc"))
    if reviewed_at is None:
        errors.append(
            f"{prefix}: contradictory_evidence_review.review_completed_at_utc must be timezone-aware ISO"
        )

    search_scope = review.get("search_scope")
    if not isinstance(search_scope, list) or not search_scope or not all(
        _substantive_text(item) for item in search_scope
    ):
        errors.append(
            f"{prefix}: contradictory_evidence_review.search_scope must be a nonempty text list"
        )

    list_fields = (
        "contradictory_evidence_ids",
        "mixed_evidence_ids",
        "late_discovered_pre_cutoff_evidence_ids",
    )
    lists: dict[str, list[str]] = {}
    for field in list_fields:
        value = review.get(field)
        if not isinstance(value, list) or not all(_substantive_text(item) for item in value):
            errors.append(f"{prefix}: contradictory_evidence_review.{field} must be a text list")
            lists[field] = []
        else:
            lists[field] = [str(item) for item in value]

    if not isinstance(review.get("reviewer_notes"), str):
        errors.append(f"{prefix}: contradictory_evidence_review.reviewer_notes must be text")

    no_contradictory = review.get("no_contradictory_evidence_found")
    if not isinstance(no_contradictory, bool):
        errors.append(
            f"{prefix}: contradictory_evidence_review.no_contradictory_evidence_found must be boolean"
        )
    elif no_contradictory and (
        lists["contradictory_evidence_ids"] or lists["mixed_evidence_ids"]
    ):
        errors.append(
            f"{prefix}: no_contradictory_evidence_found cannot be true when contradictory or mixed IDs exist"
        )
    elif not no_contradictory and not (
        lists["contradictory_evidence_ids"] or lists["mixed_evidence_ids"]
    ):
        errors.append(
            f"{prefix}: contradiction review must cite contradictory or mixed evidence, or explicitly record none found"
        )

    for evidence_id in lists["contradictory_evidence_ids"]:
        record = evidence_by_id.get(evidence_id)
        if record is None:
            errors.append(f"{prefix}: unknown contradictory evidence_id {evidence_id}")
        elif record.get("evidence_stance") != "contradicts":
            errors.append(f"{prefix}: {evidence_id} must have evidence_stance contradicts")

    for evidence_id in lists["mixed_evidence_ids"]:
        record = evidence_by_id.get(evidence_id)
        if record is None:
            errors.append(f"{prefix}: unknown mixed evidence_id {evidence_id}")
        elif record.get("evidence_stance") != "mixed":
            errors.append(f"{prefix}: {evidence_id} must have evidence_stance mixed")

    late_ids = set(lists["late_discovered_pre_cutoff_evidence_ids"])
    for evidence_id in late_ids:
        record = evidence_by_id.get(evidence_id)
        if record is None:
            errors.append(f"{prefix}: unknown late-discovered evidence_id {evidence_id}")
        elif evidence_id not in outcome_evidence_ids:
            errors.append(
                f"{prefix}: late-discovered evidence {evidence_id} must be in the outcome packet"
            )
        elif record.get("available_before_memo_seal") is not True:
            errors.append(
                f"{prefix}: late-discovered evidence {evidence_id} must have available_before_memo_seal true"
            )

    expected_late = {
        evidence_id
        for evidence_id in outcome_evidence_ids
        if evidence_by_id[evidence_id].get("available_before_memo_seal") is True
    }
    if late_ids != expected_late:
        missing_late = sorted(expected_late - late_ids)
        unexpected_late = sorted(late_ids - expected_late)
        if missing_late:
            errors.append(
                f"{prefix}: late_discovered_pre_cutoff_evidence_ids missing {missing_late}"
            )
        if unexpected_late:
            errors.append(
                f"{prefix}: late_discovered_pre_cutoff_evidence_ids include invalid IDs {unexpected_late}"
            )

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

    stance_counts: Counter[str] = Counter()
    cases_with_contradictory = 0
    cases_with_none_found = 0
    for case in cases:
        if not isinstance(case, dict):
            continue
        records: list[object] = []
        input_packet = case.get("input_packet")
        outcome_packet = case.get("outcome_packet")
        if isinstance(input_packet, dict):
            records.extend(input_packet.get("pre_cutoff_evidence_records", []))
        if isinstance(outcome_packet, dict):
            records.extend(outcome_packet.get("post_outcome_evidence_records", []))
            review = outcome_packet.get("contradictory_evidence_review")
            if isinstance(review, dict):
                if review.get("no_contradictory_evidence_found") is True:
                    cases_with_none_found += 1
                if review.get("contradictory_evidence_ids") or review.get("mixed_evidence_ids"):
                    cases_with_contradictory += 1
        for record in records:
            if isinstance(record, dict) and _substantive_text(record.get("evidence_stance")):
                stance_counts[str(record["evidence_stance"])] += 1

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
        "evidence_stance_counts": dict(sorted(stance_counts.items())),
        "cases_with_contradictory_or_mixed_evidence": cases_with_contradictory,
        "cases_with_explicit_no_contradictory_evidence_found": cases_with_none_found,
        "scores_kept_separate": True,
        "contradictory_evidence_preserved": True,
        "real_money_trading_authorized": False,
        "valid": not validate_benchmark(protocol_path, cases_path),
    }


def get_case(case_id: str, cases_path: str | Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    registry = load_case_registry(cases_path)
    for case in registry.get("cases", []):
        if isinstance(case, dict) and case.get("case_id") == case_id:
            return dict(case)
    raise KeyError(f"unknown policy benchmark case: {case_id}")
