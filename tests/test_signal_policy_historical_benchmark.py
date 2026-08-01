import json
import tempfile
import unittest
from pathlib import Path

from signal_research.policy_benchmark import (
    BENCHMARK_ID,
    REGISTRY_ID,
    interpretation_score,
    investment_score,
    load_case_registry,
    load_protocol,
    payload_hash,
    summarize_benchmark,
    validate_benchmark,
    validate_cases,
    validate_protocol,
)


class HistoricalPolicyBenchmarkTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, value: object) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_committed_protocol_and_empty_registry_are_valid(self):
        self.assertEqual([], validate_protocol())
        self.assertEqual([], validate_cases())
        self.assertEqual([], validate_benchmark())
        summary = summarize_benchmark()
        self.assertEqual(BENCHMARK_ID, summary["benchmark_id"])
        self.assertEqual(REGISTRY_ID, summary["registry_id"])
        self.assertEqual(0, summary["cases"])
        self.assertEqual(0, summary["scored_cases"])
        self.assertTrue(summary["scores_kept_separate"])
        self.assertFalse(summary["real_money_trading_authorized"])
        self.assertTrue(summary["valid"])

    def test_protocol_preserves_temporal_firewall_and_separate_scores(self):
        protocol = load_protocol()
        self.assertEqual(
            [
                "case_selection_locked",
                "point_in_time_packet_locked",
                "policy_impact_memo_sealed",
                "outcome_packet_revealed",
                "case_scored",
                "lessons_recorded",
            ],
            protocol["phase_order"],
        )
        self.assertTrue(protocol["temporal_firewall"]["memo_hash_required_before_outcome_reveal"])
        self.assertTrue(protocol["scoring"]["scores_must_remain_separate"])
        self.assertEqual(
            100,
            sum(protocol["scoring"]["interpretation_accuracy"]["component_weights"].values()),
        )
        self.assertEqual(
            100,
            sum(protocol["scoring"]["investment_usefulness"]["component_weights"].values()),
        )

    def test_case_registry_is_empty_until_selection_is_locked(self):
        registry = load_case_registry()
        self.assertEqual("awaiting_locked_case_selection", registry["status"])
        self.assertEqual([], registry["cases"])
        self.assertIn("selected and locked", registry["note"])

    def test_outcome_information_is_rejected_before_reveal(self):
        protocol = load_protocol()
        case = self.make_selected_case(stage="selected")
        case["outcome_packet"] = {"market_returns_5d": 0.10}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = self.write_json(root, "protocol.json", protocol)
            cases_path = self.write_json(root, "cases.json", self.case_registry([case]))
            errors = validate_cases(cases_path, protocol_path)
        self.assertTrue(any("outcome_packet is prohibited" in error for error in errors))

    def test_tampered_sealed_memo_hash_is_rejected(self):
        protocol = load_protocol()
        case = self.make_complete_case(protocol, stage="memo_sealed")
        case["sealed_memo"]["economic_mechanism"] = "silently rewritten after sealing"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = self.write_json(root, "protocol.json", protocol)
            cases_path = self.write_json(root, "cases.json", self.case_registry([case]))
            errors = validate_cases(cases_path, protocol_path)
        self.assertTrue(any("memo_hash does not match payload" in error for error in errors))

    def test_scored_case_keeps_interpretation_and_investment_separate(self):
        protocol = load_protocol()
        case = self.make_complete_case(protocol, stage="scored")
        interpretation_components = {
            name: maximum for name, maximum in protocol["scoring"]["interpretation_accuracy"]["component_weights"].items()
        }
        investment_components = {
            name: 0 for name in protocol["scoring"]["investment_usefulness"]["component_weights"]
        }
        case["scores"] = {
            "interpretation_accuracy": {"components": interpretation_components, "total": 100.0},
            "investment_usefulness": {"components": investment_components, "total": 0.0},
            "attribution_review": "The law was understood correctly, but the mapped exposure produced no abnormal after-cost return.",
        }
        self.assertEqual(100.0, interpretation_score(case, protocol))
        self.assertEqual(0.0, investment_score(case, protocol))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = self.write_json(root, "protocol.json", protocol)
            cases_path = self.write_json(root, "cases.json", self.case_registry([case]))
            self.assertEqual([], validate_cases(cases_path, protocol_path))

    def test_real_money_authorization_is_rejected(self):
        protocol = load_protocol()
        case = self.make_selected_case(stage="selected")
        case["real_money_trading_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = self.write_json(root, "protocol.json", protocol)
            cases_path = self.write_json(root, "cases.json", self.case_registry([case]))
            errors = validate_cases(cases_path, protocol_path)
        self.assertTrue(any("real-money trading must remain unauthorized" in error for error in errors))

    def case_registry(self, cases: list[dict]) -> dict:
        return {
            "schema_version": 1,
            "benchmark_id": BENCHMARK_ID,
            "registry_id": REGISTRY_ID,
            "status": "testing",
            "real_money_trading_authorized": False,
            "cases": cases,
        }

    def make_selected_case(self, stage: str) -> dict:
        return {
            "case_id": "POLICY-CASE-0001",
            "registry_id": REGISTRY_ID,
            "stage": stage,
            "law_name": "Synthetic historical law",
            "public_law_or_bill_identifier": "TEST-1",
            "selection_locked_at_utc": "2026-08-01T00:00:00Z",
            "event_category": "tax",
            "case_type": "intuitive trade that failed",
            "real_money_trading_authorized": False,
        }

    def make_complete_case(self, protocol: dict, stage: str) -> dict:
        case = self.make_selected_case(stage)
        input_packet = {
            "case_id": case["case_id"],
            "law_name": case["law_name"],
            "public_law_or_bill_identifier": case["public_law_or_bill_identifier"],
            "operative_text_version": "enrolled",
            "passage_timestamp_utc": "2020-01-01T00:00:00Z",
            "signature_timestamp_utc": "2020-01-02T00:00:00Z",
            "information_cutoff_utc": "2020-01-02T00:00:00Z",
            "official_text_sources": ["official://text"],
            "official_summary_sources": ["official://summary"],
            "official_fiscal_or_agency_sources": ["official://estimate"],
            "pre_cutoff_news_sources": ["news://contemporaneous"],
            "pre_cutoff_company_disclosures": ["issuer://filing"],
            "tradable_universe_at_cutoff": ["AAA", "BBB"],
            "point_in_time_financial_data_version": "v1",
        }
        input_packet["input_packet_hash"] = payload_hash(input_packet, "input_packet_hash")
        case["input_packet"] = input_packet

        memo = {
            "memo_version": 1,
            "memo_sealed_at_utc": "2020-01-02T01:00:00Z",
            "predicted_beneficiaries": ["AAA"],
            "predicted_harmed_exposures": ["BBB"],
            "predicted_no_trade_exposures": [],
            "expected_direction": {"AAA": "up", "BBB": "down"},
            "economic_mechanism": "A binding tax change alters expected cash flows.",
            "materiality_basis": "Contemporaneous official estimate.",
            "expected_realization_horizon": "5 to 60 sessions",
            "primary_trade_expression": "Long AAA, short BBB",
            "benchmark": "sector ETF",
            "entry_rule": "next regular-session open",
            "exit_rule": "fifth regular-session close",
            "invalidation_conditions": ["implementation delayed"],
            "confidence_before_outcome": 0.60,
            "known_competing_explanations": ["earnings"],
        }
        memo["memo_hash"] = payload_hash(memo, "memo_hash")
        case["sealed_memo"] = memo

        if stage in {"outcome_revealed", "scored"}:
            outcome = {
                "outcome_revealed_at_utc": "2026-08-01T00:00:00Z",
                "market_returns_1d": {"AAA": 0.01, "BBB": -0.01},
                "market_returns_5d": {"AAA": 0.02, "BBB": -0.02},
                "market_returns_20d": {"AAA": 0.03, "BBB": -0.01},
                "market_returns_60d": {"AAA": 0.04, "BBB": 0.00},
                "benchmark_returns": {"1d": 0.0, "5d": 0.0, "20d": 0.01, "60d": 0.02},
                "after_cost_abnormal_returns": {"AAA_5d": 0.018, "BBB_5d": 0.018},
                "operating_performance_changes": {"AAA": "improved", "BBB": "unchanged"},
                "company_disclosures_after_event": ["issuer://later-disclosure"],
                "mainstream_reporting_after_event": ["news://later-mainstream"],
                "trade_and_niche_reporting_after_event": ["news://later-niche"],
                "implementation_timeline": "Implemented within one year.",
                "competing_market_explanations": ["sector rally"],
            }
            outcome["outcome_packet_hash"] = payload_hash(outcome, "outcome_packet_hash")
            case["outcome_packet"] = outcome
        return case


if __name__ == "__main__":
    unittest.main()
