import json
import unittest
from pathlib import Path


class PolicyEvidenceSchemaExampleTests(unittest.TestCase):
    def test_example_preserves_contradictory_evidence_and_ai_provenance(self):
        path = Path("signal_research/policy_evidence_schema_example.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = payload["evidence_record"]
        assistance = payload["research_assistance_record"]
        review = payload["contradictory_evidence_review"]

        self.assertTrue(payload["example_only"])
        self.assertTrue(record["authors"])
        self.assertTrue(record["publisher"])
        self.assertEqual("contradicts", record["evidence_stance"])
        self.assertTrue(record["affected_claims"])
        self.assertIn(record["evidence_id"], review["contradictory_evidence_ids"])
        self.assertFalse(review["no_contradictory_evidence_found"])
        self.assertFalse(record["available_before_memo_seal"])

        self.assertEqual("google_notebooklm", assistance["tool_family"])
        self.assertIn(record["evidence_id"], assistance["input_evidence_ids"])
        self.assertTrue(assistance["source_grounding_verified"])
        self.assertTrue(assistance["human_reviewed"])
        self.assertEqual(
            "verified_against_original_sources",
            assistance["extracted_claims"][0]["verification_status"],
        )


if __name__ == "__main__":
    unittest.main()
