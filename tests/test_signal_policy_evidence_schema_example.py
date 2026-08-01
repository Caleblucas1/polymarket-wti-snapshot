import json
import unittest
from pathlib import Path


class PolicyEvidenceSchemaExampleTests(unittest.TestCase):
    def test_example_preserves_contradictory_evidence(self):
        path = Path("signal_research/policy_evidence_schema_example.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = payload["evidence_record"]
        review = payload["contradictory_evidence_review"]
        self.assertTrue(payload["example_only"])
        self.assertEqual("contradicts", record["evidence_stance"])
        self.assertTrue(record["affected_claims"])
        self.assertIn(record["evidence_id"], review["contradictory_evidence_ids"])
        self.assertFalse(review["no_contradictory_evidence_found"])
        self.assertFalse(record["available_before_memo_seal"])


if __name__ == "__main__":
    unittest.main()
