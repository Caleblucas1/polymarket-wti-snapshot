from __future__ import annotations

import json
import re
from pathlib import Path

from .governance import capital_rights, component_confidence_score, production_gate
from .models import SignalCandidate, SignalStage


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "signal_candidates.json"
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


def load_candidates(
    path: str | Path = DEFAULT_REGISTRY, *, validate: bool = True
) -> list[SignalCandidate]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 2:
        raise ValueError("unsupported signal registry schema")
    candidates = [SignalCandidate.from_dict(item) for item in raw["signals"]]

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
