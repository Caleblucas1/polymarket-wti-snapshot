import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "signal_research" / "results" / "S-012-BTC-QQQ-RV-RESULT.json"
SHADOW = ROOT / "signal_records" / "live" / "S-012-BTC-QQQ-RV-SHADOW.json"


class S012ResultTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(RESULT.read_text(encoding="utf-8"))
        self.shadow = json.loads(SHADOW.read_text(encoding="utf-8"))

    def test_final_classification_preserves_research_only_boundary(self):
        self.assertEqual(
            "prospective_shadow_watchlist_historical_support_not_independent_proof",
            self.result["classification"],
        )
        self.assertFalse(self.result["real_money_trading_authorized"])
        self.assertFalse(self.result["production_stage_permitted"])
        self.assertEqual("none", self.result["capital_rights"])

    def test_primary_inference_uses_nonoverlapping_events(self):
        primary = self.result["primary_90_day_result"][
            "nonoverlapping_primary_inference"
        ]
        self.assertEqual(6, primary["events"])
        self.assertGreater(primary["relative_improvement_vs_abs_expected_mean"], 0.25)
        self.assertGreater(primary["one_sided_matched_null_probability"], 0.05)
        self.assertLess(primary["worst_max_adverse_excursion"], -0.49)

    def test_source_exposed_validation_is_not_mislabeled_untouched(self):
        validation = self.result["primary_90_day_result"][
            "source_exposed_validation_nonoverlapping"
        ]
        self.assertEqual(2, validation["events"])
        self.assertIn("not untouched", validation["warning"])
        self.assertEqual(
            "2026-08-04",
            self.result["historical_scope"]["prospective_untouched_start"],
        )

    def test_shadow_is_armed_without_a_prospective_event(self):
        self.assertEqual("armed_or_waiting_for_fresh_crossover", self.shadow["status"])
        self.assertEqual(0, self.shadow["prospective_event_count"])
        self.assertFalse(
            self.shadow["latest_comparable_observation"]["btc_below_qqq"]
        )
        self.assertFalse(self.shadow["real_money_trading_authorized"])

    def test_artifact_hashes_are_sha256(self):
        provenance = self.result["artifact_provenance"]
        for key in (
            "historical_artifact_sha256",
            "audit_artifact_sha256",
            "shadow_artifact_sha256",
            "btc_source_payload_sha256",
            "qqq_source_payload_sha256",
        ):
            value = provenance[key]
            self.assertEqual(64, len(value))
            int(value, 16)
        self.assertEqual(64, len(hashlib.sha256(RESULT.read_bytes()).hexdigest()))


if __name__ == "__main__":
    unittest.main()
