import json
import unittest
from pathlib import Path

from signal_research.governance import capital_rights
from signal_research.hypotheses import get_hypothesis, load_hypotheses
from signal_research.registry import get_candidate


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ID = "POLICY-US-LEGISLATION-001"


class LegislativePolicyAlphaTests(unittest.TestCase):
    def test_old_semiconductor_label_resolves_to_broader_policy_signal(self):
        item = get_candidate("POLICY-SEMIS-001")
        self.assertEqual(REGISTRY_ID, item.registry_id)
        self.assertEqual("U.S. legislative policy alpha", item.name)
        self.assertEqual("hypothesis", item.stage.value)
        self.assertEqual("ready_for_data", item.operational_status.value)
        self.assertEqual("research_only", capital_rights(item))
        self.assertEqual(24, item.confidence_score)

    def test_canonical_post_passage_rule_is_frozen_and_pre_passage_is_blocked(self):
        rows = [row for row in load_hypotheses() if row["registry_id"] == REGISTRY_ID]
        canonical = next(row for row in rows if row["variant"] == "canonical")
        enhanced = next(row for row in rows if row["variant"] == "enhanced")

        self.assertEqual("frozen", canonical["freeze_status"])
        self.assertEqual([], canonical["blocking_fields"])
        self.assertIn("no post-event price information", canonical["entry_rule"])
        self.assertIn("all five pre-entry gates", canonical["trigger_rule"])
        self.assertEqual("blocked", enhanced["freeze_status"])
        self.assertIsNone(enhanced["entry_rule"])
        self.assertIn("mechanical passage-probability threshold", enhanced["blocking_fields"])

    def test_registry_evidence_and_live_status_use_new_durable_id(self):
        evidence = [
            json.loads(line)
            for line in (ROOT / "signal_records" / "evidence_ledger.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        policy_evidence = [row for row in evidence if row["registry_id"] == REGISTRY_ID]
        self.assertEqual(2, len(policy_evidence))
        self.assertFalse(any(row["registry_id"] == "POLICY-SEMIS-001" for row in evidence))

        live = json.loads(
            (ROOT / "signal_records" / "live_status.json").read_text(encoding="utf-8")
        )
        row = next(row for row in live["signals"] if row["registry_id"] == REGISTRY_ID)
        self.assertEqual("research_only", row["capital_right"])
        self.assertFalse(row["real_money_authorized"])

    def test_alias_returns_frozen_canonical_hypothesis(self):
        value = get_hypothesis("GOV-SEMIS-001")
        self.assertEqual(REGISTRY_ID, value["registry_id"])
        self.assertTrue(value["dataset_eligible"])
        self.assertEqual("frozen", value["freeze_status"])


if __name__ == "__main__":
    unittest.main()
