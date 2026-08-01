import json
import tempfile
import unittest
from pathlib import Path

from signal_research.policy_benchmark import (
    BENCHMARK_ID,
    REGISTRY_ID,
    payload_hash,
    validate_cases,
)


class PolicyEvidenceOfficialTextTests(unittest.TestCase):
    def test_empty_pre_cutoff_evidence_is_rejected(self):
        protocol_path = Path("signal_research/policy_historical_benchmark.json")
        case = {
            "case_id": "POLICY-CASE-EMPTY-EVIDENCE",
            "registry_id": REGISTRY_ID,
            "stage": "packet_locked",
            "law_name": "Synthetic law",
            "public_law_or_bill_identifier": "TEST-EMPTY",
            "selection_locked_at_utc": "2026-08-01T00:00:00Z",
            "event_category": "tax",
            "case_type": "diffuse or no-trade effect",
            "real_money_trading_authorized": False,
            "input_packet": {
                "case_id": "POLICY-CASE-EMPTY-EVIDENCE",
                "law_name": "Synthetic law",
                "public_law_or_bill_identifier": "TEST-EMPTY",
                "operative_text_version": "enrolled",
                "passage_timestamp_utc": "2020-01-01T00:00:00Z",
                "signature_timestamp_utc": "2020-01-02T00:00:00Z",
                "information_cutoff_utc": "2020-01-02T00:00:00Z",
                "pre_cutoff_evidence_records": [],
                "research_assistance_records": [],
                "tradable_universe_at_cutoff": ["AAA"],
                "point_in_time_financial_data_version": "v1",
            },
        }
        case["input_packet"]["input_packet_hash"] = payload_hash(
            case["input_packet"], "input_packet_hash"
        )
        registry = {
            "schema_version": 3,
            "benchmark_id": BENCHMARK_ID,
            "registry_id": REGISTRY_ID,
            "status": "testing",
            "real_money_trading_authorized": False,
            "cases": [case],
        }
        with tempfile.TemporaryDirectory() as directory:
            cases_path = Path(directory) / "cases.json"
            cases_path.write_text(json.dumps(registry), encoding="utf-8")
            errors = validate_cases(cases_path, protocol_path)
        self.assertTrue(
            any(
                "at least one official_text evidence record is required" in error
                for error in errors
            )
        )


if __name__ == "__main__":
    unittest.main()
