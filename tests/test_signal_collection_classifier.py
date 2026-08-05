import unittest

from signal_collection_classifier import (
    CROSS_CHOKEPOINT_RULE,
    classify_signal_collection,
    evidence_metadata,
)
from signal_review import build_observation_record


def row(event_id, change, bullish_direction, *, key=None):
    return {
        "key": key or f"{event_id}::{change}",
        "event_id": event_id,
        "header": event_id,
        "change_7d_pp": change,
        "bullish_direction": bullish_direction,
        "signal_scope": "active_contract",
        "status": "open",
    }


class SignalCollectionClassifierTests(unittest.TestCase):
    def test_diplomacy_and_blockade_are_indirect_not_flow_confirmation(self):
        for event_id in ("us_iran_peace_talks", "iran_blockade_ends"):
            metadata = evidence_metadata(event_id)
            self.assertEqual(metadata["domain"], "political_normalization")
            self.assertEqual(metadata["flow_relevance"], "indirect")

    def test_bab_el_mandeb_inference_is_allowed_but_not_automatic(self):
        self.assertIn("may inform the prior", CROSS_CHOKEPOINT_RULE)
        self.assertIn("must not be assumed", CROSS_CHOKEPOINT_RULE)
        self.assertNotIn("prohibit", CROSS_CHOKEPOINT_RULE.lower())

    def test_normalization_and_price_evidence_prevent_stale_bullish_label(self):
        signals = [
            row("iran_blockade_ends", 16, "down"),
            row("us_iran_peace_talks", 7, "down"),
            row("wti_july_2026", 18, "down"),
            row("crude_oil_ath", -8, "up"),
            row("houthis_target_shipping_july_22", 20, "up"),
        ]
        result = classify_signal_collection(signals)
        self.assertEqual(result["label"], "mixed/caution")
        self.assertTrue(result["concentrated_physical_risk_tail"])
        self.assertIn("do not call this broad oil-bullish confirmation", result["interpretation"])

    def test_bearish_confirmation_requires_independent_breadth(self):
        signals = [
            row("iran_blockade_ends", 12, "down"),
            row("us_iran_peace_talks", 8, "down"),
            row("wti_july_2026", 15, "down"),
            row("bab_el_mandeb_closed", -7, "up"),
        ]
        result = classify_signal_collection(signals)
        self.assertEqual(result["label"], "oil-bearish confirmation")
        self.assertGreaterEqual(len(result["bearish_domains"]), 2)

    def test_many_correlated_houthi_contracts_count_as_one_event(self):
        signals = [
            row("houthis_target_shipping_july_22", 20 + i / 10, "up", key=f"h::{i}")
            for i in range(30)
        ]
        signals += [
            row("iran_blockade_ends", 15, "down"),
            row("wti_july_2026", 15, "down"),
        ]
        result = classify_signal_collection(signals)
        self.assertEqual(result["used_event_count"], 3)
        self.assertEqual(result["label"], "mixed/caution")

    def test_two_independent_bullish_domains_confirm(self):
        signals = [
            row("iran_targets_shipping", 10, "up"),
            row("wti_july_2026", 9, "up"),
        ]
        result = classify_signal_collection(signals)
        self.assertEqual(result["label"], "oil-bullish confirmation")

    def test_durable_record_overrides_stale_caller_label(self):
        signals = [
            row("iran_blockade_ends", 12, "down"),
            row("wti_july_2026", 14, "down"),
            row("bab_el_mandeb_closed", -6, "up"),
        ]
        record = build_observation_record(
            as_of_et="2026-08-05T09:15:00-04:00",
            signals=signals,
            signal_level="oil-bullish confirmation",
            catalog={"events": {}},
        )
        self.assertEqual(record["signal_level"], "oil-bearish confirmation")
        self.assertEqual(record["reported_signal_level"], "oil-bullish confirmation")
        self.assertEqual(record["classification"]["version"], "balanced-collection-v2")
        self.assertEqual(record["signals"][0]["flow_relevance"], "indirect")


if __name__ == "__main__":
    unittest.main()
