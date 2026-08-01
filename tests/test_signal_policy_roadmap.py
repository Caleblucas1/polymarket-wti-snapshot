import json
import tempfile
import unittest
from pathlib import Path

from signal_research.policy_roadmap import (
    EXPECTED_KEYS,
    historical_readiness,
    load_roadmap,
    summarize_roadmap,
    validate_roadmap,
)


class PolicyRoadmapTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_committed_eight_step_roadmap_is_valid(self):
        self.assertEqual([], validate_roadmap())
        roadmap = load_roadmap()
        self.assertEqual(list(range(1, 9)), [step["step"] for step in roadmap["steps"]])
        self.assertEqual(EXPECTED_KEYS, [step["key"] for step in roadmap["steps"]])
        self.assertEqual("completed", roadmap["steps"][0]["status"])
        self.assertEqual("ready_to_start", roadmap["steps"][1]["status"])
        self.assertEqual("blocked_by_readiness_gate", roadmap["steps"][7]["status"])
        self.assertFalse(roadmap["real_money_trading_authorized"])

    def test_current_readiness_is_honestly_blocked(self):
        readiness = historical_readiness()
        self.assertFalse(readiness["passed"])
        self.assertIn("minimum_selected_cases", readiness["failures"])
        self.assertIn("minimum_scored_cases", readiness["failures"])
        self.assertIn("minimum_mean_interpretation_accuracy", readiness["failures"])
        self.assertEqual("research_only", readiness["capital_right_after_pass"])
        self.assertFalse(readiness["real_money_trading_authorized"])

    def test_summary_exposes_all_steps_and_no_prospective_cases(self):
        summary = summarize_roadmap()
        self.assertEqual(8, len(summary["steps"]))
        self.assertEqual(0, summary["framework_revisions"])
        self.assertEqual(0, summary["prospective_cases"])
        self.assertEqual("blocked_until_historical_readiness_gate", summary["prospective_status"])
        self.assertTrue(summary["valid"])
        self.assertFalse(summary["real_money_trading_authorized"])

    def test_reordered_steps_are_rejected(self):
        roadmap = load_roadmap()
        roadmap["steps"][1], roadmap["steps"][2] = roadmap["steps"][2], roadmap["steps"][1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roadmap_path = self.write_json(root, "roadmap.json", roadmap)
            errors = validate_roadmap(roadmap_path=roadmap_path)
        self.assertTrue(any("step keys or order" in error for error in errors))

    def test_retrospective_framework_revision_is_rejected(self):
        revisions = {
            "schema_version": 1,
            "roadmap_id": "POLICY-ROADMAP-001",
            "registry_id": "POLICY-US-LEGISLATION-001",
            "real_money_trading_authorized": False,
            "error_taxonomy": ["materiality"],
            "records": [
                {
                    "revision_id": "REV-001",
                    "created_at_utc": "2026-08-01T00:00:00Z",
                    "source_case_ids": ["CASE-001"],
                    "error_taxonomy": "materiality",
                    "problem_observed": "Materiality was overstated.",
                    "change_made": "Tighten the materiality rule.",
                    "version_before": 1,
                    "version_after": 2,
                    "applies_prospectively_only": False,
                    "original_results_preserved": False
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revisions_path = self.write_json(root, "revisions.json", revisions)
            errors = validate_roadmap(revisions_path=revisions_path)
        self.assertTrue(any("must apply prospectively only" in error for error in errors))
        self.assertTrue(any("must preserve original results" in error for error in errors))

    def test_prospective_case_before_readiness_is_rejected(self):
        prospective = {
            "schema_version": 1,
            "roadmap_id": "POLICY-ROADMAP-001",
            "registry_id": "POLICY-US-LEGISLATION-001",
            "status": "active",
            "activation_timestamp_utc": "2026-08-01T00:00:00Z",
            "real_money_trading_authorized": False,
            "cases": [
                {
                    "case_id": "PROSPECTIVE-001",
                    "first_observed_at_utc": "2026-08-02T00:00:00Z",
                    "information_cutoff_utc": "2026-08-02T00:00:00Z",
                    "public_law_or_bill_identifier": "TEST-1",
                    "memo_hash": "abc",
                    "real_money_trading_authorized": False
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prospective_path = self.write_json(root, "prospective.json", prospective)
            errors = validate_roadmap(prospective_path=prospective_path)
        self.assertTrue(any("cannot begin before the historical readiness gate" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
