"""Definitions for the uniform active-contract signal layer.

An event page is a container. A dated, threshold, or day-specific market on
that page is the exact contract that can be used as evidence. This module
keeps those two identities separate and supplies the directional interpretation
needed by the oil read-through without combining contracts into baskets.
"""

from __future__ import annotations

import re
from typing import Any

from signal_collection_classifier import evidence_metadata


ACTIVE_CONTRACT_DEFINITION_VERSION = "all-active-contracts-v1"

# These are the first contracts the questionnaire examined. They are a
# highlighted view only; they are not a privileged or authoritative subset.
HIGHLIGHTED_CONTRACT_KEYS = frozenset(
    {
        "peace_talks_aug_31",
        "blockade_near_term",
        "blockade_long_term",
        "bab_el_mandeb_closed_aug_31",
        "wti_100_july",
    }
)

# Default direction means: when the exact contract's Yes probability rises,
# does that add an oil-bullish impulse? Labels with threshold directionality
# are handled by contract_bullish_direction below.
EVENT_SIGNAL_POLICIES: dict[str, dict[str, str]] = {
    "hormuz_normal_by_july_31": {
        "default_bullish_direction": "down",
        "subject": "Hormuz-normalization odds",
        "rationale": "More normalization is oil-bearish.",
    },
    "wti_july_2026": {
        "default_bullish_direction": "up",
        "subject": "WTI threshold odds",
        "rationale": "Higher upward price thresholds are oil-bullish; lower-price thresholds are oil-bearish.",
    },
    "crude_oil_ath": {
        "default_bullish_direction": "up",
        "subject": "crude-oil tail-risk odds",
        "rationale": "A new all-time-high outcome is oil-bullish.",
    },
    "israel_iran_ceasefire": {
        "default_bullish_direction": "down",
        "subject": "ceasefire-continuation odds",
        "rationale": "More durable ceasefire odds are oil-bearish.",
    },
    "us_invades_iran": {
        "default_bullish_direction": "up",
        "subject": "invasion-risk odds",
        "rationale": "Higher direct-conflict odds are oil-bullish.",
    },
    "iran_blockade_ends": {
        "default_bullish_direction": "down",
        "subject": "blockade-normalization odds",
        "rationale": (
            "More blockade-ending odds are generally oil-bearish political/legal normalization, "
            "but they do not prove vessel traffic has normalized in Hormuz or Bab el-Mandeb."
        ),
    },
    "us_iran_nuclear_deal": {
        "default_bullish_direction": "down",
        "subject": "nuclear-deal odds",
        "rationale": "More diplomatic normalization is oil-bearish.",
    },
    "iran_hormuz_fees": {
        "default_bullish_direction": "up",
        "subject": "Hormuz-friction odds",
        "rationale": "More fee-enforcement odds indicate greater physical friction.",
    },
    "bab_el_mandeb_closed": {
        "default_bullish_direction": "up",
        "subject": "Bab el-Mandeb closure odds",
        "rationale": "More closure odds are oil-bullish.",
    },
    "iran_gulf_action": {
        "default_bullish_direction": "up",
        "subject": "Iran–Gulf-action odds",
        "rationale": "More military-action odds are oil-bullish.",
    },
    "us_iran_peace_talks": {
        "default_bullish_direction": "down",
        "subject": "peace-talk odds",
        "rationale": (
            "More diplomacy odds are generally oil-bearish absent a separate escalation signal, "
            "but they do not directly confirm vessel flow in Hormuz or Bab el-Mandeb."
        ),
    },
    "hormuz_transit_july_20": {
        "default_bullish_direction": "down",
        "subject": "Hormuz-transit odds",
        "rationale": "More normal transit is oil-bearish; a low-transit bucket is treated as physical-risk bullish.",
    },
    "hormuz_transit_july_27": {
        "default_bullish_direction": "down",
        "subject": "Hormuz-transit odds",
        "rationale": "More normal transit is oil-bearish; a low-transit bucket is treated as physical-risk bullish.",
    },
    "zero_hormuz_transit": {
        "default_bullish_direction": "up",
        "subject": "zero-transit odds",
        "rationale": "More zero-transit odds are oil-bullish.",
    },
    "bab_el_mandeb_average_transit": {
        "default_bullish_direction": "down",
        "subject": "Bab el-Mandeb transit odds",
        "rationale": "More normal transit is oil-bearish; a low-transit bucket is treated as physical-risk bullish.",
    },
    "iran_targets_shipping": {
        "default_bullish_direction": "up",
        "subject": "Iranian shipping-attack odds",
        "rationale": "More successful-attack odds are oil-bullish.",
    },
    "houthis_target_shipping_july_22": {
        "default_bullish_direction": "up",
        "subject": "Houthi shipping-attack odds",
        "rationale": "More qualifying attack odds are oil-bullish.",
    },
}


def _label(market: dict[str, Any]) -> str:
    return str(
        market.get("label")
        or market.get("groupItemTitle")
        or market.get("question")
        or "Unnamed contract"
    ).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unnamed"


def exact_contract_key(event_id: str, market: dict[str, Any]) -> str:
    """Return a stable exact-contract key, retaining physical contract identity."""
    condition_id = (
        market.get("condition_id")
        or market.get("conditionId")
        or market.get("id")
        or market.get("token")
        or market.get("token_id")
    )
    if condition_id:
        return f"{event_id}::{condition_id}"
    return f"{event_id}::label:{_slug(_label(market))}"


def _is_low_transit_bucket(label: str) -> bool:
    normalized = label.lower()
    return any(
        marker in normalized
        for marker in ("<", "less than", "under ", "0–", "0-", "zero")
    )


def contract_bullish_direction(event_id: str, market: dict[str, Any]) -> str:
    """Return ``up`` or ``down`` for the exact contract's Yes probability."""
    policy = EVENT_SIGNAL_POLICIES.get(event_id)
    if policy is None:
        raise KeyError(f"No oil-direction policy configured for {event_id!r}")
    label = _label(market)
    normalized = label.lower()
    if event_id == "wti_july_2026":
        if normalized.startswith(("↓", "down", "below", "under")):
            return "down"
        return "up"
    if event_id in {"hormuz_transit_july_20", "hormuz_transit_july_27", "bab_el_mandeb_average_transit"}:
        return "up" if _is_low_transit_bucket(label) else "down"
    return policy["default_bullish_direction"]


def contract_signal_metadata(event_id: str, market: dict[str, Any]) -> dict[str, str]:
    """Return exact-contract identity, direction, and evidence-scope metadata."""
    policy = EVENT_SIGNAL_POLICIES.get(event_id)
    if policy is None:
        raise KeyError(f"No oil-direction policy configured for {event_id!r}")
    label = _label(market)
    condition_id = str(
        market.get("condition_id")
        or market.get("conditionId")
        or market.get("id")
        or ""
    ).strip() or None
    token_id = str(market.get("token_id") or market.get("token") or "").strip() or None
    direction = contract_bullish_direction(event_id, market)
    evidence = evidence_metadata(event_id)
    return {
        "key": exact_contract_key(event_id, market),
        "event_id": event_id,
        "contract_id": condition_id or "",
        "token_id": token_id or "",
        "contract_label": label,
        "bullish_direction": direction,
        "subject": policy["subject"],
        "direction_rationale": policy["rationale"],
        "signal_scope": "active_contract",
        "evidence_domain": evidence["domain"],
        "flow_relevance": evidence["flow_relevance"],
        "geography": evidence["geography"],
        "independence_group": evidence["independence_group"],
        "cross_chokepoint_rule": evidence["cross_chokepoint_rule"],
    }


def validate_catalog_events(catalog: dict[str, Any]) -> None:
    """Ensure every supplied event has a policy and no event is omitted."""
    event_ids = set(catalog.get("events", {}))
    policy_ids = set(EVENT_SIGNAL_POLICIES)
    missing = sorted(event_ids - policy_ids)
    extra = sorted(policy_ids - event_ids)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing policies: {', '.join(missing)}")
        if extra:
            details.append(f"policies without catalog events: {', '.join(extra)}")
        raise ValueError("Catalog/event policy mismatch; " + "; ".join(details))


def validate_exact_signal_rows(signals: list[dict[str, Any]]) -> None:
    """Reject silently merged or duplicated exact-contract rows."""
    keys = [str(signal.get("key", "")) for signal in signals]
    if any(not key for key in keys):
        raise ValueError("Every active contract signal requires a stable key")
    if len(keys) != len(set(keys)):
        raise ValueError("Active contract signals must have unique exact-contract keys")
    for signal in signals:
        if signal.get("signal_scope") != "active_contract":
            raise ValueError("Every row in the active-contract layer must have signal_scope=active_contract")
