"""Balanced collection-level classifier for Polymarket oil signals.

The classifier treats exact contracts as evidence but aggregates them first by
logical event and then by independent evidence domain. This prevents a large
family of correlated dated contracts from acting like independent votes.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from typing import Any, Iterable

CLASSIFICATION_VERSION = "balanced-collection-v2"

EVENT_EVIDENCE: dict[str, dict[str, str]] = {
    "hormuz_normal_by_july_31": {"domain": "hormuz_physical_flow", "flow_relevance": "direct", "geography": "Strait of Hormuz"},
    "wti_july_2026": {"domain": "oil_price_distribution", "flow_relevance": "market_confirmation", "geography": "global oil"},
    "crude_oil_ath": {"domain": "oil_price_distribution", "flow_relevance": "market_confirmation", "geography": "global oil"},
    "israel_iran_ceasefire": {"domain": "political_normalization", "flow_relevance": "indirect", "geography": "Israel-Iran"},
    "us_invades_iran": {"domain": "direct_conflict", "flow_relevance": "indirect", "geography": "U.S.-Iran"},
    "iran_blockade_ends": {"domain": "political_normalization", "flow_relevance": "indirect", "geography": "U.S.-Iran/Hormuz policy"},
    "us_iran_nuclear_deal": {"domain": "political_normalization", "flow_relevance": "indirect", "geography": "U.S.-Iran"},
    "iran_hormuz_fees": {"domain": "hormuz_physical_flow", "flow_relevance": "direct", "geography": "Strait of Hormuz"},
    "bab_el_mandeb_closed": {"domain": "bab_el_mandeb_physical_flow", "flow_relevance": "direct", "geography": "Bab el-Mandeb"},
    "iran_gulf_action": {"domain": "hormuz_security_risk", "flow_relevance": "direct_risk", "geography": "Persian Gulf/Strait of Hormuz"},
    "us_iran_peace_talks": {"domain": "political_normalization", "flow_relevance": "indirect", "geography": "U.S.-Iran"},
    "hormuz_transit_july_20": {"domain": "hormuz_physical_flow", "flow_relevance": "direct", "geography": "Strait of Hormuz"},
    "hormuz_transit_july_27": {"domain": "hormuz_physical_flow", "flow_relevance": "direct", "geography": "Strait of Hormuz"},
    "zero_hormuz_transit": {"domain": "hormuz_physical_flow", "flow_relevance": "direct", "geography": "Strait of Hormuz"},
    "bab_el_mandeb_average_transit": {"domain": "bab_el_mandeb_physical_flow", "flow_relevance": "direct", "geography": "Bab el-Mandeb"},
    "iran_targets_shipping": {"domain": "hormuz_security_risk", "flow_relevance": "direct_risk", "geography": "Persian Gulf/Strait of Hormuz"},
    "houthis_target_shipping_july_22": {"domain": "bab_el_mandeb_security_risk", "flow_relevance": "direct_risk", "geography": "Red Sea/Bab el-Mandeb"},
}

DOMAIN_WEIGHTS = {
    "oil_price_distribution": 1.35,
    "hormuz_physical_flow": 1.25,
    "bab_el_mandeb_physical_flow": 1.25,
    "hormuz_security_risk": 1.15,
    "bab_el_mandeb_security_risk": 1.15,
    "direct_conflict": 1.0,
    "political_normalization": 0.9,
}

CROSS_CHOKEPOINT_RULE = (
    "U.S.-Iran diplomacy, blockade policy, and Hormuz developments may inform the prior "
    "for Bab el-Mandeb, but they must not be assumed to produce the same traffic outcome. "
    "Treat Bab el-Mandeb flow as separately confirmable evidence."
)


def evidence_metadata(event_id: str) -> dict[str, str]:
    policy = EVENT_EVIDENCE.get(event_id)
    if policy is None:
        raise KeyError(f"No evidence-domain policy configured for {event_id!r}")
    return {
        **policy,
        "cross_chokepoint_rule": CROSS_CHOKEPOINT_RULE,
        "independence_group": event_id,
    }


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _oil_impulse(signal: dict[str, Any]) -> float | None:
    change = _number(signal.get("change_7d_pp"))
    if change is None:
        change = _number(signal.get("change_7d"))
    if change is None:
        change = _number(signal.get("change_1d_pp"))
    if change is None:
        change = _number(signal.get("change_1d"))
    direction = signal.get("bullish_direction")
    if change is None or direction not in {"up", "down"}:
        return None
    impulse = change if direction == "up" else -change
    return max(-25.0, min(25.0, impulse))


def _median(values: list[float]) -> float:
    return round(float(statistics.median(values)), 2)


def classify_signal_collection(signals: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Recompute the collection label from current exact-contract moves.

    Exact contracts are aggregated by event before domains are scored, so a
    recurring event with dozens of dated contracts does not overwhelm
    independent evidence.
    """
    by_event: dict[str, list[float]] = defaultdict(list)
    event_domains: dict[str, str] = {}
    used_rows = 0
    for signal in signals:
        if str(signal.get("status", "open")).lower() not in {"open", "active"}:
            continue
        event_id = str(signal.get("event_id") or "").strip()
        if not event_id or event_id not in EVENT_EVIDENCE:
            continue
        impulse = _oil_impulse(signal)
        if impulse is None:
            continue
        by_event[event_id].append(impulse)
        event_domains[event_id] = EVENT_EVIDENCE[event_id]["domain"]
        used_rows += 1

    event_scores = {event_id: _median(values) for event_id, values in by_event.items()}
    by_domain: dict[str, list[float]] = defaultdict(list)
    for event_id, score in event_scores.items():
        by_domain[event_domains[event_id]].append(score)
    domain_scores = {domain: _median(values) for domain, values in by_domain.items()}

    weighted = [(score, DOMAIN_WEIGHTS.get(domain, 1.0)) for domain, score in domain_scores.items()]
    total_weight = sum(weight for _, weight in weighted)
    overall = round(sum(score * weight for score, weight in weighted) / total_weight, 2) if total_weight else 0.0

    bullish_domains = sorted(domain for domain, score in domain_scores.items() if score >= 3.0)
    bearish_domains = sorted(domain for domain, score in domain_scores.items() if score <= -3.0)
    conflict = bool(bullish_domains and bearish_domains)

    physical_bullish = max(
        (score for domain, score in domain_scores.items() if "physical_flow" in domain or "security_risk" in domain),
        default=0.0,
    )
    normalization_bearish = domain_scores.get("political_normalization", 0.0) <= -3.0
    price_bearish = domain_scores.get("oil_price_distribution", 0.0) <= -3.0
    concentrated_tail = physical_bullish >= 4.0 and (normalization_bearish or price_bearish)

    if conflict:
        label = "mixed/caution"
    elif overall >= 4.0 and len(bullish_domains) >= 2:
        label = "oil-bullish confirmation"
    elif overall <= -4.0 and len(bearish_domains) >= 2:
        label = "oil-bearish confirmation"
    else:
        label = "limited confirmation"

    if concentrated_tail:
        interpretation = (
            "Broad normalization or WTI-downside evidence conflicts with a concentrated "
            "physical-risk tail; do not call this broad oil-bullish confirmation."
        )
    elif label == "oil-bullish confirmation":
        interpretation = "At least two independent evidence domains confirm an oil-bullish move."
    elif label == "oil-bearish confirmation":
        interpretation = "At least two independent evidence domains confirm an oil-bearish move."
    elif label == "mixed/caution":
        interpretation = "Independent evidence domains point in opposing directions."
    else:
        interpretation = "The collection lacks broad independent confirmation in either direction."

    canonical = json.dumps(
        {"version": CLASSIFICATION_VERSION, "event_scores": event_scores, "domain_scores": domain_scores},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": CLASSIFICATION_VERSION,
        "label": label,
        "overall_score": overall,
        "event_scores": event_scores,
        "domain_scores": domain_scores,
        "bullish_domains": bullish_domains,
        "bearish_domains": bearish_domains,
        "concentrated_physical_risk_tail": concentrated_tail,
        "interpretation": interpretation,
        "used_contract_rows": used_rows,
        "used_event_count": len(event_scores),
        "input_hash": hashlib.sha256(canonical).hexdigest(),
        "cross_chokepoint_rule": CROSS_CHOKEPOINT_RULE,
    }
