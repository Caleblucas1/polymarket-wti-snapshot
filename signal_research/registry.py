from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .governance import capital_rights, component_confidence_score, production_gate
from .models import SignalCandidate, SignalStage


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "signal_candidates.json"
DEFAULT_EXTENSION_DIR = Path(__file__).resolve().parent / "registry_extensions"
REGISTRY_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-[0-9]{3}$")


def validate_candidate(candidate: SignalCandidate) -> list[str]:
    errors: list[str] = []
    if not REGISTRY_ID_PATTERN.fullmatch(candidate.registry_id):
        errors.append(f"{candidate.signal_id}: invalid registry_id {candidate.registry_id!r}")
    if not candidate.source_urls:
        errors.append(f"{candidate.registry_id}: at least one source URL is required")
    if not candidate.hypothesis.strip():
        errors.append(f"{candidate.registry_id}: hypothesis is required")
    if not candidate.applicable_regimes:
        errors.append(f"{candidate.registry_id}: applicable regimes are required")
    if not candidate.invalid_regimes:
        errors.append(f"{candidate.registry_id}: invalid regimes are required")

    try:
        computed = component_confidence_score(candidate.confidence_components)
    except ValueError as exc:
        errors.append(f"{candidate.registry_id}: {exc}")
    else:
        if abs(computed - candidate.confidence_score) > 1e-9:
            errors.append(
                f"{candidate.registry_id}: confidence_score={candidate.confidence_score} "
                f"does not match components={computed}"
            )

    if candidate.stage in {
        SignalStage.HYPOTHESIS,
        SignalStage.BACKTEST,
        SignalStage.PRODUCTION,
    } and not candidate.canonical_rule.strip():
        errors.append(f"{candidate.registry_id}: canonical_rule is required after Candidate")

    if candidate.stage is SignalStage.PRODUCTION:
        gate = production_gate(candidate)
        if not gate.valid_current_production:
            errors.append(
                f"{candidate.registry_id}: invalid production signal; failed "
                + ", ".join(gate.failures)
            )
    if capital_rights(candidate) == "capped_live" and candidate.stage is not SignalStage.PRODUCTION:
        errors.append(f"{candidate.registry_id}: live capital rights require Production stage")
    return errors


def _is_default_registry(path: str | Path) -> bool:
    return Path(path).resolve() == DEFAULT_REGISTRY.resolve()


def _extension_rows(directory: Path = DEFAULT_EXTENSION_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: registry extension must be a JSON object")
        row = raw.get("signal", raw)
        if not isinstance(row, dict):
            raise ValueError(f"{path}: signal must be a JSON object")
        rows.append(dict(row))
    return rows


def load_candidates(
    path: str | Path = DEFAULT_REGISTRY, *, validate: bool = True
) -> list[SignalCandidate]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 2:
        raise ValueError("unsupported signal registry schema")
    rows = list(raw["signals"])
    if _is_default_registry(path):
        rows.extend(_extension_rows())
    candidates = [SignalCandidate.from_dict(item) for item in rows]

    for field in ("signal_id", "registry_id"):
        values = [getattr(candidate, field) for candidate in candidates]
        if len(values) != len(set(values)):
            raise ValueError(f"{field} values must be unique")

    lookup_names: list[str] = []
    for candidate in candidates:
        lookup_names.extend([candidate.signal_id, candidate.registry_id, *candidate.aliases])
    if len(lookup_names) != len(set(lookup_names)):
        raise ValueError("signal IDs, registry IDs and aliases must not collide")

    if validate:
        errors = [
            error
            for candidate in candidates
            for error in validate_candidate(candidate)
        ]
        if errors:
            raise ValueError("invalid signal registry:\n- " + "\n- ".join(errors))
    return candidates


def get_candidate(
    identifier: str, path: str | Path = DEFAULT_REGISTRY
) -> SignalCandidate:
    for candidate in load_candidates(path):
        if identifier in {
            candidate.signal_id,
            candidate.registry_id,
            *candidate.aliases,
        }:
            return candidate
    raise KeyError(identifier)


def validate_registry(path: str | Path = DEFAULT_REGISTRY) -> list[str]:
    try:
        load_candidates(path, validate=True)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return [str(exc)]
    return []
