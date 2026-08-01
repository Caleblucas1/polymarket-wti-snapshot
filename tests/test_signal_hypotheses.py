import json
import tempfile
import unittest
from pathlib import Path

from signal_research.hypotheses import (
    get_hypothesis,
    hypothesis_fingerprint,
    load_hypotheses,
    statuses,
    summarize_statuses,
    validate_hypotheses,
)


class SignalHypothesisTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_current_hypotheses_are_valid_and_cover_registry(self):
        self.assertEqual([], validate_hypotheses())
        summary = summarize_statuses(statuses())
        self.assertEqual(8, summary["total"])
        self.assertEqual(6, summary["frozen_canonical"])
        self.assertEqual(2, summary["blocked_canonical"])
        self.assertEqual(6, summary["dataset_eligible"])
        self.assertFalse(summary["real_money_trading_authorized"])

    def test_blocked_records_preserve_missing_information_instead_of_inventing_it(self):
        rows = {row["registry_id"]: row for row in load_hypotheses()}
        self.assertEqual("blocked", rows["POLICY-SEMIS-001"]["freeze_status"])
        self.assertIn("expected return direction", rows["POLICY-SEMIS-001"]["blocking_fields"])
        self.assertIsNone(rows["POLICY-SEMIS-001"]["entry_rule"])
        self.assertEqual("blocked", rows["CROSS-ASSET-REBOUND-001"]["freeze_status"])
        self.assertIn(
            "mechanical common-shock detector",
            rows["CROSS-ASSET-REBOUND-001"]["blocking_fields"],
        )

    def test_frozen_hypothesis_is_resolvable_by_legacy_id_and_has_fingerprint(self):
        value = get_hypothesis("S-010")
        self.assertEqual("FLOW-MON-BTC-001", value["registry_id"])
        self.assertEqual("frozen", value["freeze_status"])
        self.assertTrue(value["dataset_eligible"])
        self.assertEqual(64, len(value["fingerprint"]))

    def test_fingerprint_changes_when_definition_changes(self):
        row = get_hypothesis("TECH-HMA-001")
        original = hypothesis_fingerprint(row)
        changed = dict(row)
        changed.pop("fingerprint", None)
        changed.pop("dataset_eligible", None)
        changed["exit_rule"] = changed["exit_rule"] + " changed"
        self.assertNotEqual(original, hypothesis_fingerprint(changed))

    def test_validator_rejects_frozen_record_with_blockers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.write_json(
                root,
                "registry.json",
                {"signals": [{"registry_id": "A"}]},
            )
            row = {
                "registry_id": "A",
                "definition_version": 1,
                "variant": "canonical",
                "freeze_status": "frozen",
                "definition_origin": "test",
                "source_claim": "claim",
                "decision_information": "known data",
                "target_instrument": "asset",
                "entry_rule": "enter",
                "exit_rule": "exit",
                "direction_rule": "long",
                "trigger_rule": "trigger",
                "benchmark": "benchmark",
                "applicable_regimes": ["all"],
                "invalid_regimes": ["missing data"],
                "cost_model": "costs",
                "deactivation_rule": "stop",
                "out_of_sample_boundary": "future",
                "timezone": "UTC",
                "bar_size": "1d",
                "blocking_fields": ["still missing"],
                "source_fidelity_notes": "notes",
            }
            hypotheses = self.write_json(
                root,
                "hypotheses.json",
                {
                    "governing_principle": "canonical_before_enhanced",
                    "policy": {"real_money_trading_authorized": False},
                    "hypotheses": [row],
                },
            )
            errors = validate_hypotheses(hypotheses, registry)
            self.assertTrue(any("frozen hypotheses cannot have blocking_fields" in error for error in errors))

    def test_validator_rejects_enhanced_before_frozen_canonical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.write_json(
                root,
                "registry.json",
                {"signals": [{"registry_id": "A"}]},
            )
            common = {
                "registry_id": "A",
                "definition_origin": "test",
                "source_claim": "claim",
                "decision_information": "known data",
                "target_instrument": "asset",
                "entry_rule": "enter",
                "exit_rule": "exit",
                "direction_rule": "long",
                "trigger_rule": "trigger",
                "benchmark": "benchmark",
                "applicable_regimes": ["all"],
                "invalid_regimes": ["missing data"],
                "cost_model": "costs",
                "deactivation_rule": "stop",
                "out_of_sample_boundary": "future",
                "timezone": "UTC",
                "bar_size": "1d",
                "source_fidelity_notes": "notes",
            }
            canonical = {
                **common,
                "definition_version": 1,
                "variant": "canonical",
                "freeze_status": "blocked",
                "blocking_fields": ["entry approval"],
            }
            enhanced = {
                **common,
                "definition_version": 1,
                "variant": "enhanced",
                "freeze_status": "frozen",
                "blocking_fields": [],
            }
            hypotheses = self.write_json(
                root,
                "hypotheses.json",
                {
                    "governing_principle": "canonical_before_enhanced",
                    "policy": {"real_money_trading_authorized": False},
                    "hypotheses": [canonical, enhanced],
                },
            )
            errors = validate_hypotheses(hypotheses, registry)
            self.assertTrue(any("cannot freeze before canonical" in error for error in errors))

    def test_validator_rejects_missing_registry_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self.write_json(
                root,
                "registry.json",
                {"signals": [{"registry_id": "A"}, {"registry_id": "B"}]},
            )
            hypotheses = self.write_json(
                root,
                "hypotheses.json",
                {
                    "governing_principle": "canonical_before_enhanced",
                    "policy": {"real_money_trading_authorized": False},
                    "hypotheses": [],
                },
            )
            errors = validate_hypotheses(hypotheses, registry)
            self.assertIn("missing hypothesis record for A", errors)
            self.assertIn("missing hypothesis record for B", errors)


if __name__ == "__main__":
    unittest.main()
