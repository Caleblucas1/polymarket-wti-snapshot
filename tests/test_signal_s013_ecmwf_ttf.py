import json
import unittest
from pathlib import Path

from signal_research.evaluate_s013_ecmwf_ttf_candidate import evaluate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "signal_research" / "inputs" / "S-013-ECMWF-WARM-WINTER-TTF-SOURCE.json"
RESULT = ROOT / "signal_research" / "results" / "S-013-ECMWF-WARM-WINTER-TTF-RESULT.json"
SHADOW = ROOT / "signal_records" / "live" / "S-013-ECMWF-WARM-WINTER-TTF-SHADOW.json"


class S013CandidateTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.result = json.loads(RESULT.read_text(encoding="utf-8"))
        self.shadow = json.loads(SHADOW.read_text(encoding="utf-8"))

    def test_missing_data_blocks_backtest_without_rejecting_candidate(self):
        result = evaluate(self.source)
        self.assertTrue(result["candidate_accepted"])
        self.assertFalse(result["data_readiness"]["canonical_trigger_evaluable"])
        self.assertFalse(result["data_readiness"]["backtest_executable"])
        self.assertEqual(
            "candidate_accepted_hypothesis_blocked_market_data_unavailable",
            result["classification"],
        )
        self.assertIsNone(result["backtest_results"])
        self.assertIsNone(result["shadow_position"])

    def test_canonical_rule_is_mechanical_and_not_pixel_based(self):
        rule = self.result["canonical_rule"]
        self.assertEqual("35N-60N, 10W-30E", rule["region"])
        self.assertIn(">= 60%", rule["trigger"])
        self.assertEqual("short", rule["direction"])
        self.assertEqual(0.05, rule["round_trip_cost_eur_per_mwh"])
        self.assertNotIn("pixel", rule["trigger"].lower())

    def test_embedded_el_nino_claim_is_excluded(self):
        excluded = self.result["excluded_evidence"]
        self.assertEqual(1, len(excluded))
        self.assertIn("El Nino", excluded[0]["claim"])

    def test_research_boundary_is_explicit(self):
        self.assertEqual(32, self.result["confidence_score"])
        self.assertEqual("none", self.result["capital_rights"])
        self.assertFalse(self.result["real_money_trading_authorized"])
        self.assertIsNone(self.shadow["position"])
        self.assertFalse(self.shadow["canonical_trigger_evaluable"])
        self.assertFalse(self.shadow["real_money_trading_authorized"])

    def test_identity_mismatch_is_rejected(self):
        bad = dict(self.source)
        bad["signal_id"] = "S-999"
        with self.assertRaises(ValueError):
            evaluate(bad)


if __name__ == "__main__":
    unittest.main()
