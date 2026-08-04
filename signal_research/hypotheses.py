from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .registry import load_candidates


DEFAULT_HYPOTHESES_PATH = Path("signal_hypotheses.json")
DEFAULT_REGISTRY_PATH = Path("signal_candidates.json")
DEFAULT_EXTENSION_DIR = Path(__file__).resolve().parent / "hypothesis_extensions"
ALLOWED_FREEZE_STATUSES = {"blocked", "frozen", "retired"}
ALLOWED_VARIANTS = {"canonical", "enhanced"}
PLACEHOLDER_TOKENS = {"tbd", "todo", "unknown", "later", "n/a", "na"}

REQUIRED_COMMON_FIELDS = (
    "registry_id",
    "definition_version",
    "variant",
    "freeze_status",
    "definition_origin",
    "source_claim",
    "decision_information",
    "target_instrument",
    "benchmark",
    "applicable_regimes",
    "invalid_regimes",
    "deactivation_rule",
    "timezone",
    "bar_size",
    "blocking_fields",
    "source_fidelity_notes",
)

REQUIRED_FROZEN_FIELDS = (
    "entry_rule",
    "exit_rule",
    "direction_rule",
    "trigger_rule",
    "cost_model",
    "out_of_sample_boundary",
)


@dataclass(frozen=True)
class HypothesisStatus:
    registry_id: str
    definition_version: int
    variant: str
    freeze_status: str
    fingerprint: str
    dataset_eligible: bool
    blocking_fields: tuple[str, ...]


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _is_default_hypotheses(path: str | Path) -> bool:
    return Path(path).resolve() == DEFAULT_HYPOTHESES_PATH.resolve()


def _extension_rows(directory: Path = DEFAULT_EXTENSION_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.json")):
        raw = _read_json(path)
        row = raw.get("hypothesis", raw)
        if not isinstance(row, dict):
            raise ValueError(f"{path}: hypothesis must be a JSON object")
        rows.append(dict(row))
    return rows


def load_hypotheses(path: str | Path = DEFAULT_HYPOTHESES_PATH) -> list[dict[str, Any]]:
    raw = _read_json(path)
    rows = raw.get("hypotheses")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: hypotheses must be a list")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: every hypothesis must be an object")
    result = [dict(row) for row in rows]
    if _is_default_hypotheses(path):
        result.extend(_extension_rows())
    return result


def canonical_payload(row: dict[str, Any]) -> bytes:
    excluded = {"fingerprint"}
    value = {key: row[key] for key in sorted(row) if key not in excluded}
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def hypothesis_fingerprint(row: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(row)).hexdigest()


def _nonempty_text(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return value.strip().lower() not in PLACEHOLDER_TOKENS


def _validate_row(row: dict[str, Any], index: int) -> list[str]:
    prefix = f"hypotheses[{index}]"
    errors: list[str] = []
    for key in REQUIRED_COMMON_FIELDS:
        if key not in row:
            errors.append(f"{prefix}: missing required field {key}")

    registry_id = row.get("registry_id")
    if not _nonempty_text(registry_id):
        errors.append(f"{prefix}: registry_id must be nonempty")

    version = row.get("definition_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append(f"{prefix}: definition_version must be a positive integer")

    variant = row.get("variant")
    if variant not in ALLOWED_VARIANTS:
        errors.append(f"{prefix}: invalid variant {variant!r}")

    status = row.get("freeze_status")
    if status not in ALLOWED_FREEZE_STATUSES:
        errors.append(f"{prefix}: invalid freeze_status {status!r}")

    for key in (
        "definition_origin",
        "source_claim",
        "decision_information",
        "target_instrument",
        "benchmark",
        "deactivation_rule",
        "timezone",
        "bar_size",
        "source_fidelity_notes",
    ):
        if key in row and not _nonempty_text(row.get(key)):
            errors.append(f"{prefix}: {key} must be substantive text")

    for key in ("applicable_regimes", "invalid_regimes", "blocking_fields"):
        value = row.get(key)
        if not isinstance(value, list) or not all(_nonempty_text(item) for item in value):
            errors.append(f"{prefix}: {key} must be a list of substantive strings")

    blocking = row.get("blocking_fields") if isinstance(row.get("blocking_fields"), list) else []
    if status == "blocked" and not blocking:
        errors.append(f"{prefix}: blocked hypotheses must list blocking_fields")
    if status == "frozen":
        if blocking:
            errors.append(f"{prefix}: frozen hypotheses cannot have blocking_fields")
        for key in REQUIRED_FROZEN_FIELDS:
            if not _nonempty_text(row.get(key)):
                errors.append(f"{prefix}: frozen hypothesis requires substantive {key}")
    return errors


def validate_hypotheses(
    hypotheses_path: str | Path = DEFAULT_HYPOTHESES_PATH,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> list[str]:
    errors: list[str] = []
    hypotheses_raw = _read_json(hypotheses_path)

    if hypotheses_raw.get("governing_principle") != "canonical_before_enhanced":
        errors.append("hypothesis file must declare canonical_before_enhanced")
    policy = hypotheses_raw.get("policy")
    if not isinstance(policy, dict) or policy.get("real_money_trading_authorized") is not False:
        errors.append("hypothesis file must explicitly prohibit real-money authorization")

    try:
        rows = load_hypotheses(hypotheses_path)
    except ValueError as exc:
        return errors + [str(exc)]
    try:
        registry_ids = {
            candidate.registry_id
            for candidate in load_candidates(registry_path, validate=False)
        }
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return errors + [f"invalid registry: {exc}"]

    seen_versions: set[tuple[str, str, int]] = set()
    canonical_by_id: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        errors.extend(_validate_row(row, index))
        rid = row.get("registry_id")
        version = row.get("definition_version")
        variant = row.get("variant")
        if isinstance(rid, str) and isinstance(version, int) and isinstance(variant, str):
            key = (rid, variant, version)
            if key in seen_versions:
                errors.append(f"duplicate hypothesis definition {key}")
            seen_versions.add(key)
        if rid not in registry_ids:
            errors.append(f"hypothesis references unknown registry_id {rid}")
        if variant == "canonical" and isinstance(rid, str):
            canonical_by_id.setdefault(rid, []).append(row)

    row_ids = {row.get("registry_id") for row in rows if isinstance(row.get("registry_id"), str)}
    for rid in sorted(registry_ids - row_ids):
        errors.append(f"missing hypothesis record for {rid}")

    for rid in sorted(registry_ids):
        canonical_rows = canonical_by_id.get(rid, [])
        if len(canonical_rows) != 1:
            errors.append(f"{rid} must have exactly one active canonical definition; found {len(canonical_rows)}")

    frozen_canonical_ids = {
        row.get("registry_id")
        for row in rows
        if row.get("variant") == "canonical" and row.get("freeze_status") == "frozen"
    }
    for row in rows:
        if row.get("variant") == "enhanced" and row.get("freeze_status") == "frozen":
            rid = row.get("registry_id")
            if rid not in frozen_canonical_ids:
                errors.append(f"enhanced hypothesis for {rid} cannot freeze before canonical")

    return errors


def statuses(path: str | Path = DEFAULT_HYPOTHESES_PATH) -> list[HypothesisStatus]:
    result: list[HypothesisStatus] = []
    for row in load_hypotheses(path):
        blocking = row.get("blocking_fields", [])
        result.append(
            HypothesisStatus(
                registry_id=str(row.get("registry_id", "")),
                definition_version=int(row.get("definition_version", 0)),
                variant=str(row.get("variant", "")),
                freeze_status=str(row.get("freeze_status", "")),
                fingerprint=hypothesis_fingerprint(row),
                dataset_eligible=(
                    row.get("variant") == "canonical"
                    and row.get("freeze_status") == "frozen"
                    and not blocking
                ),
                blocking_fields=tuple(str(item) for item in blocking),
            )
        )
    return result


def get_hypothesis(
    identifier: str,
    hypotheses_path: str | Path = DEFAULT_HYPOTHESES_PATH,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    aliases: dict[str, str] = {}
    for candidate in load_candidates(registry_path, validate=False):
        aliases[candidate.registry_id] = candidate.registry_id
        aliases[candidate.signal_id] = candidate.registry_id
        for alias in candidate.aliases:
            aliases[alias] = candidate.registry_id
    rid = aliases.get(identifier, identifier)
    matches = [row for row in load_hypotheses(hypotheses_path) if row.get("registry_id") == rid]
    if not matches:
        raise KeyError(f"unknown hypothesis identifier: {identifier}")
    canonical = [row for row in matches if row.get("variant") == "canonical"]
    if len(canonical) != 1:
        raise ValueError(f"{rid} does not have exactly one canonical hypothesis")
    row = canonical[0]
    return {
        **row,
        "fingerprint": hypothesis_fingerprint(row),
        "dataset_eligible": row.get("freeze_status") == "frozen" and not row.get("blocking_fields"),
    }


def summarize_statuses(rows: Iterable[HypothesisStatus]) -> dict[str, Any]:
    values = list(rows)
    return {
        "total": len(values),
        "frozen_canonical": sum(
            row.variant == "canonical" and row.freeze_status == "frozen" for row in values
        ),
        "blocked_canonical": sum(
            row.variant == "canonical" and row.freeze_status == "blocked" for row in values
        ),
        "dataset_eligible": sum(row.dataset_eligible for row in values),
        "real_money_trading_authorized": False,
        "signals": [
            {
                "registry_id": row.registry_id,
                "definition_version": row.definition_version,
                "variant": row.variant,
                "freeze_status": row.freeze_status,
                "dataset_eligible": row.dataset_eligible,
                "blocking_fields": list(row.blocking_fields),
                "fingerprint": row.fingerprint,
            }
            for row in values
        ],
    }
