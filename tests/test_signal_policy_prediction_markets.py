import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "signal_research" / "policy_prediction_markets.json"


class PolicyPredictionMarketDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_record_is_bound_to_legislative_policy_signal(self):
        self.assertEqual(
            "POLICY-US-LEGISLATION-001",
            self.config["registry_id"],
        )
        self.assertEqual("pre_passage_enhanced", self.config["variant"])
        self.assertEqual(
            "approved_research_input_not_frozen",
            self.config["status"],
        )

    def test_single_probability_is_not_treated_as_expected_passage_date(self):
        rules = " ".join(self.config["interpretation_rules"]).lower()
        prohibited = " ".join(self.config["prohibited_uses"]).lower()
        self.assertIn("not automatically an expected passage date", rules)
        self.assertIn("do not treat one deadline probability", prohibited)
        self.assertIn("passage-probability term structure", rules)

    def test_contract_milestones_cannot_be_conflated(self):
        checks = " ".join(self.config["required_contract_checks"]).lower()
        self.assertIn("house passage", checks)
        self.assertIn("senate passage", checks)
        self.assertIn("final congressional passage", checks)
        self.assertIn("presidential signature", checks)

    def test_executable_market_quality_is_required(self):
        fields = set(self.config["prospective_data_fields"])
        for required in {
            "yes_bid",
            "yes_ask",
            "yes_midpoint",
            "last_trade_price",
            "spread",
            "liquidity",
            "volume",
            "snapshot_timestamp_utc",
            "resolution_milestone",
        }:
            self.assertIn(required, fields)

    def test_polymarket_cannot_be_the_only_trigger(self):
        prohibited = " ".join(self.config["prohibited_uses"]).lower()
        rules = " ".join(self.config["interpretation_rules"]).lower()
        self.assertIn("sole trade trigger", prohibited)
        self.assertIn("supplements official legislative text", rules)

    def test_record_never_authorizes_real_money(self):
        self.assertFalse(self.config["real_money_trading_authorized"])

    def test_freeze_blockers_remain_explicit(self):
        blockers = set(self.config["remaining_freeze_blockers"])
        self.assertIn("minimum liquidity and volume thresholds", blockers)
        self.assertIn("maximum acceptable spread", blockers)
        self.assertIn("multi-deadline term-structure calculation", blockers)
        self.assertIn("untouched out-of-sample boundary", blockers)


if __name__ == "__main__":
    unittest.main()
