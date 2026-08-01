import json
import tempfile
import unittest
from pathlib import Path

from signal_research.priorities import (
    APPROVED_FLOW_TEST_ID,
    CROSS_ASSET_ID,
    EXPECTED_CROSS_ASSET_BLOCKERS,
    FLOW_MONTH_ID,
    discover_flow_month_configs,
    load_priorities,
    summarize_priorities,
    validate_priorities,
)


class SignalResearchPriorityTests(unittest.TestCase):
    def test_committed_reprioritization_is_valid(self):
        self.assertEqual([], validate_priorities())
        summary = summarize_priorities()
        self.assertTrue(summary["valid"])
        self.assertEqual(CROSS_ASSET_ID, summary["highest_priority"])
        self.assertFalse(summary["highest_priority_live_launch_authorized"])
        self.assertFalse(summary["monthly_flow_future_launches_enabled"])
        self.assertEqual("dormant", summary["monthly_flow_post_test_status"])
        self.assertFalse(summary["real_money_trading_authorized"])

    def test_cross_asset_priority_preserves_all_canonical_blockers(self):
        priorities = load_priorities()
        cross = priorities["signals"][CROSS_ASSET_ID]
        self.assertEqual(1, cross["priority_rank"])
        self.assertEqual("design_blocked_next_live_candidate", cross["status"])
        self.assertEqual(EXPECTED_CROSS_ASSET_BLOCKERS, cross["current_blockers"])
        self.assertFalse(cross["live_launch_authorized"])
        self.assertIn("unweighted", cross["canonical_aggregation"])
        self.assertIn("volatility-weighted", cross["experimental_aggregation"])

    def test_monthly_flow_is_one_off_infrastructure_only(self):
        priorities = load_priorities()
        flow = priorities["signals"][FLOW_MONTH_ID]
        self.assertEqual("low_priority_infrastructure_only", flow["priority_tier"])
        self.assertEqual(APPROVED_FLOW_TEST_ID, flow["current_one_off_test_id"])
        self.assertTrue(flow["current_one_off_must_complete_honestly"])
        self.assertFalse(flow["future_month_launches_enabled"])
        self.assertFalse(flow["automatic_successor_creation_enabled"])
        self.assertEqual("none", flow["capital_rights_from_current_test"])

    def test_only_august_2026_monthly_flow_config_exists(self):
        self.assertEqual([APPROVED_FLOW_TEST_ID], discover_flow_month_configs())

    def test_validator_rejects_future_month_config(self):
        priorities = load_priorities()
        hypotheses = json.loads(Path("signal_hypotheses.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            priorities_path = root / "priorities.json"
            hypotheses_path = root / "hypotheses.json"
            live_dir = root / "live_tests"
            live_dir.mkdir()
            priorities_path.write_text(json.dumps(priorities), encoding="utf-8")
            hypotheses_path.write_text(json.dumps(hypotheses), encoding="utf-8")
            (live_dir / f"{APPROVED_FLOW_TEST_ID}.json").write_text("{}", encoding="utf-8")
            (live_dir / "FLOW-MON-BTC-2026-09.json").write_text("{}", encoding="utf-8")
            errors = validate_priorities(priorities_path, hypotheses_path, live_dir)
        self.assertTrue(any("unapproved FLOW-MON-BTC" in error for error in errors))

    def test_validator_rejects_silent_cross_asset_unblocking(self):
        priorities = load_priorities()
        hypotheses = json.loads(Path("signal_hypotheses.json").read_text(encoding="utf-8"))
        for row in hypotheses["hypotheses"]:
            if row["registry_id"] == CROSS_ASSET_ID and row["variant"] == "canonical":
                row["freeze_status"] = "frozen"
                row["blocking_fields"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            priorities_path = root / "priorities.json"
            hypotheses_path = root / "hypotheses.json"
            live_dir = root / "live_tests"
            live_dir.mkdir()
            priorities_path.write_text(json.dumps(priorities), encoding="utf-8")
            hypotheses_path.write_text(json.dumps(hypotheses), encoding="utf-8")
            (live_dir / f"{APPROVED_FLOW_TEST_ID}.json").write_text("{}", encoding="utf-8")
            errors = validate_priorities(priorities_path, hypotheses_path, live_dir)
        self.assertTrue(any("must not silently unfreeze" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
