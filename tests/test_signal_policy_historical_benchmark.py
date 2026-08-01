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

    def validate_synthetic_case(self, case: dict) -> list[str]:
        protocol = load_protocol()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol_path = self.write_json(root, "protocol.json", protocol)
            cases_path = self.write_json(root, "cases.json", self.case_registry([case]))
            return validate_cases(cases_path, protocol_path)

    def test_committed_protocol_and_empty_registry_are_valid(self):
        self.assertEqual([], validate_protocol())
        self.assertEqual([], validate_cases())
        self.assertEqual([], validate_benchmark())
        summary = summarize_benchmark()
        self.assertEqual(BENCHMARK_ID, summary["benchmark_id"])
        self.assertEqual(REGISTRY_ID, summary["registry_id"])
        self.assertEqual(0, summary["cases"])
        self.assertEqual(0, summary["scored_cases"])
        self.assertEqual({}, summary["evidence_stance_counts"])
        self.assertEqual({}, summary["research_assistance_counts"])
        self.assertTrue(summary["source_author_and_publisher_tagging_required"])
        self.assertTrue(summary["ai_output_is_not_evidence"])
        self.assertTrue(summary["contradictory_evidence_preserved"])
        self.assertFalse(summary["real_money_trading_authorized"])
        self.assertTrue(summary["valid"])

    def test_protocol_requires_authors_stance_and_ai_disclosure(self):
        protocol = load_protocol()
        evidence_schema = protocol["evidence_record_schema"]
        assistance_schema = protocol["research_assistance_schema"]
        self.assertEqual(3, protocol["schema_version"])
        self.assertIn("authors", evidence_schema["required_fields"])
        self.assertIn("publisher", evidence_schema["required_fields"])
        self.assertEqual(
            {"supports", "contradicts", "mixed", "neutral_context"},
            set(evidence_schema["allowed_stances"]),
        )
        self.assertEqual(
            {"google_notebooklm", "google_gemini", "other"},
            set(assistance_schema["allowed_tool_families"]),
        )
        self.assertIn("input_evidence_ids", assistance_schema["required_fields"])
        self.assertIn("human_reviewed", assistance_schema["required_fields"])
        self.assertIn(
            "late_discovered_pre_cutoff_evidence_ids",
            protocol["required_contradictory_evidence_review_fields"],
        )
        self.assertTrue(
            protocol["temporal_firewall"]["source_author_and_publisher_required"]
        )
        self.assertTrue(
            protocol["temporal_firewall"]["ai_research_assistance_disclosure_required"]
        )

    def test_case_registry_is_empty_until_selection_is_locked(self):
        registry = load_case_registry()
        self.assertEqual(3, registry["schema_version"])
        self.assertEqual("awaiting_locked_case_selection", registry["status"])
        self.assertEqual([], registry["cases"])
        self.assertIn("selected and locked", registry["note"])

    def test_outcome_information_is_rejected_before_reveal(self):
        case = self.make_selected_case(stage="selected")
        case["outcome_packet"] = {"market_returns_5d": 0.10}
        errors = self.validate_synthetic_case(case)
        self.assertTrue(any("outcome_packet is prohibited" in error for error in errors))

    def test_tampered_sealed_memo_hash_is_rejected(self):
        case = self.make_complete_case(stage="memo_sealed")
        case["sealed_memo"]["economic_mechanism"] = "silently rewritten after sealing"
        errors = self.validate_synthetic_case(case)
        self.assertTrue(any("memo_hash does not match payload" in error for error in errors))

    def test_scored_case_keeps_interpretation_and_investment_separate(self):
        protocol = load_protocol()
        case = self.make_complete_case(stage="scored")
        interpretation_components = {
            name: maximum
            for name, maximum in protocol["scoring"]["interpretation_accuracy"][
                "component_weights"
            ].items()
        }
        investment_components = {
            name: 0
            for name in protocol["scoring"]["investment_usefulness"][
                "component_weights"
            ]
        }
        case["scores"] = {
            "interpretation_accuracy": {
                "components": interpretation_components,
                "total": 100.0,
            },
            "investment_usefulness": {
                "components": investment_components,
                "total": 0.0,
            },
            "attribution_review": "The law was understood correctly, but the mapped exposure produced no abnormal after-cost return.",
        }
        self.assertEqual(100.0, interpretation_score(case, protocol))
        self.assertEqual(0.0, investment_score(case, protocol))
        self.assertEqual([], self.validate_synthetic_case(case))

    def test_real_money_authorization_is_rejected(self):
        case = self.make_selected_case(stage="selected")
        case["real_money_trading_authorized"] = True
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("real-money trading must remain unauthorized" in error for error in errors)
        )

    def test_unstructured_source_lists_are_rejected(self):
        case = self.make_complete_case(stage="memo_sealed")
        case["input_packet"]["pre_cutoff_evidence_records"] = ["news://unsupported"]
        self.rehash(case["input_packet"], "input_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(any("evidence record must be an object" in error for error in errors))

    def test_source_requires_author_tag(self):
        case = self.make_complete_case(stage="memo_sealed")
        record = case["input_packet"]["pre_cutoff_evidence_records"][0]
        record["authors"] = []
        self.rehash(case["input_packet"], "input_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("authors must be a nonempty list" in error for error in errors)
        )

    def test_contradictory_evidence_must_name_affected_claims(self):
        case = self.make_complete_case(stage="outcome_revealed")
        record = case["outcome_packet"]["post_outcome_evidence_records"][0]
        record["affected_claims"] = []
        self.rehash(case["outcome_packet"], "outcome_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("contradicts evidence must identify affected_claims" in error for error in errors)
        )

    def test_contradiction_review_must_cite_found_evidence(self):
        case = self.make_complete_case(stage="outcome_revealed")
        review = case["outcome_packet"]["contradictory_evidence_review"]
        review["contradictory_evidence_ids"] = []
        review["no_contradictory_evidence_found"] = False
        self.rehash(case["outcome_packet"], "outcome_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("must cite contradictory or mixed evidence" in error for error in errors)
        )

    def test_contradiction_review_rejects_stance_mismatch(self):
        case = self.make_complete_case(stage="outcome_revealed")
        record = case["outcome_packet"]["post_outcome_evidence_records"][0]
        record["evidence_stance"] = "supports"
        self.rehash(case["outcome_packet"], "outcome_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("must have evidence_stance contradicts" in error for error in errors)
        )

    def test_late_discovered_pre_cutoff_evidence_cannot_be_hidden(self):
        case = self.make_complete_case(stage="outcome_revealed")
        record = case["outcome_packet"]["post_outcome_evidence_records"][0]
        record["published_at_utc"] = "2019-12-31T12:00:00Z"
        record["available_before_memo_seal"] = True
        review = case["outcome_packet"]["contradictory_evidence_review"]
        review["late_discovered_pre_cutoff_evidence_ids"] = []
        self.rehash(case["outcome_packet"], "outcome_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("late_discovered_pre_cutoff_evidence_ids missing" in error for error in errors)
        )

    def test_explicit_none_found_review_is_valid(self):
        case = self.make_complete_case(stage="outcome_revealed")
        record = case["outcome_packet"]["post_outcome_evidence_records"][0]
        record["evidence_stance"] = "neutral_context"
        record["affected_claims"] = []
        review = case["outcome_packet"]["contradictory_evidence_review"]
        review["contradictory_evidence_ids"] = []
        review["mixed_evidence_ids"] = []
        review["no_contradictory_evidence_found"] = True
        review["reviewer_notes"] = (
            "Search completed; no source materially contradicted the sealed claims."
        )
        self.rehash(case["outcome_packet"], "outcome_packet_hash")
        self.assertEqual([], self.validate_synthetic_case(case))

    def test_post_cutoff_source_cannot_enter_input_packet(self):
        case = self.make_complete_case(stage="memo_sealed")
        record = case["input_packet"]["pre_cutoff_evidence_records"][0]
        record["published_at_utc"] = "2020-01-03T00:00:00Z"
        self.rehash(case["input_packet"], "input_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(any("published after its packet cutoff" in error for error in errors))

    def test_valid_notebooklm_assistance_is_audited_not_evidence(self):
        case = self.make_complete_case(stage="memo_sealed")
        case["input_packet"]["research_assistance_records"] = [
            self.research_assistance_record(
                "AI-INPUT-001",
                tool_family="google_notebooklm",
                temporal_role="pre_cutoff_research",
                input_evidence_ids=["EVID-INPUT-001"],
            )
        ]
        self.rehash(case["input_packet"], "input_packet_hash")
        self.assertEqual([], self.validate_synthetic_case(case))

    def test_ai_assistance_cannot_reference_unregistered_source(self):
        case = self.make_complete_case(stage="memo_sealed")
        record = self.research_assistance_record(
            "AI-INPUT-UNKNOWN",
            tool_family="google_gemini",
            temporal_role="pre_cutoff_research",
            input_evidence_ids=["EVID-NOT-REGISTERED"],
        )
        case["input_packet"]["research_assistance_records"] = [record]
        self.rehash(case["input_packet"], "input_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(any("unknown input evidence_id" in error for error in errors))

    def test_unresolved_ai_claim_cannot_enter_locked_packet(self):
        case = self.make_complete_case(stage="memo_sealed")
        record = self.research_assistance_record(
            "AI-INPUT-UNRESOLVED",
            tool_family="google_gemini",
            temporal_role="pre_cutoff_research",
            input_evidence_ids=["EVID-INPUT-001"],
        )
        record["extracted_claims"][0]["verification_status"] = "unresolved"
        case["input_packet"]["research_assistance_records"] = [record]
        self.rehash(case["input_packet"], "input_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(
            any("unresolved AI-generated claims cannot enter" in error for error in errors)
        )

    def test_ai_assistance_requires_human_review_and_source_grounding(self):
        case = self.make_complete_case(stage="memo_sealed")
        record = self.research_assistance_record(
            "AI-INPUT-UNREVIEWED",
            tool_family="google_notebooklm",
            temporal_role="pre_cutoff_research",
            input_evidence_ids=["EVID-INPUT-001"],
        )
        record["source_grounding_verified"] = False
        record["human_reviewed"] = False
        case["input_packet"]["research_assistance_records"] = [record]
        self.rehash(case["input_packet"], "input_packet_hash")
        errors = self.validate_synthetic_case(case)
        self.assertTrue(any("source grounding must be verified" in error for error in errors))
        self.assertTrue(any("must be human reviewed" in error for error in errors))

    def case_registry(self, cases: list[dict]) -> dict:
        return {
            "schema_version": 3,
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

    def evidence_record(
        self,
        evidence_id: str,
        *,
        source_type: str,
        stance: str,
        temporal_role: str,
        published_at: str,
        available_before_memo_seal: bool,
        affected_claims: list[str],
    ) -> dict:
        return {
            "evidence_id": evidence_id,
            "source_url": f"https://example.test/{evidence_id}",
            "title": f"Evidence {evidence_id}",
            "authors": [
                "United States Congress"
                if source_type == "official_text"
                else "Synthetic Reporter"
            ],
            "publisher": "Synthetic Source",
            "published_at_utc": published_at,
            "accessed_at_utc": "2026-08-01T00:00:00Z",
            "source_type": source_type,
            "evidence_stance": stance,
            "affected_claims": affected_claims,
            "temporal_role": temporal_role,
            "available_before_memo_seal": available_before_memo_seal,
            "reliability": "primary" if source_type == "official_text" else "high",
            "summary": "Synthetic evidence used to test source-level audit rules.",
            "archive_reference": f"sha256:{evidence_id}",
            "notes": "",
        }

    def research_assistance_record(
        self,
        assistance_id: str,
        *,
        tool_family: str,
        temporal_role: str,
        input_evidence_ids: list[str],
    ) -> dict:
        source_id = input_evidence_ids[0]
        return {
            "assistance_id": assistance_id,
            "tool_family": tool_family,
            "tool_name": (
                "Google NotebookLM"
                if tool_family == "google_notebooklm"
                else "Google Gemini"
            ),
            "model_or_version": "unknown_not_exposed",
            "workspace_reference": f"workspace:{assistance_id}",
            "used_at_utc": "2026-08-01T00:00:00Z",
            "temporal_role": temporal_role,
            "task": "Compare the registered sources and extract a candidate legal-mechanism claim.",
            "input_evidence_ids": input_evidence_ids,
            "output_artifact_reference": f"sha256:{assistance_id}",
            "extracted_claims": [
                {
                    "claim": "The law changes expected cash flows through a binding tax mechanism.",
                    "source_evidence_ids": [source_id],
                    "verification_status": "verified_against_original_sources",
                }
            ],
            "source_grounding_verified": True,
            "human_reviewed": True,
            "verification_notes": "The claim was checked against the original registered source.",
            "notes": "",
        }

    def rehash(self, payload: dict, hash_field: str) -> None:
        payload[hash_field] = payload_hash(payload, hash_field)

    def make_complete_case(self, stage: str) -> dict:
        case = self.make_selected_case(stage)
        input_packet = {
            "case_id": case["case_id"],
            "law_name": case["law_name"],
            "public_law_or_bill_identifier": case[
                "public_law_or_bill_identifier"
            ],
            "operative_text_version": "enrolled",
            "passage_timestamp_utc": "2020-01-01T00:00:00Z",
            "signature_timestamp_utc": "2020-01-02T00:00:00Z",
            "information_cutoff_utc": "2020-01-02T00:00:00Z",
            "pre_cutoff_evidence_records": [
                self.evidence_record(
                    "EVID-INPUT-001",
                    source_type="official_text",
                    stance="supports",
                    temporal_role="pre_cutoff_input",
                    published_at="2020-01-01T00:00:00Z",
                    available_before_memo_seal=True,
                    affected_claims=["operative text and legal mechanism"],
                )
            ],
            "research_assistance_records": [],
            "tradable_universe_at_cutoff": ["AAA", "BBB"],
            "point_in_time_financial_data_version": "v1",
        }
        self.rehash(input_packet, "input_packet_hash")
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
        self.rehash(memo, "memo_hash")
        case["sealed_memo"] = memo

        if stage in {"outcome_revealed", "scored"}:
            contradictory_id = "EVID-OUTCOME-CONTRA-001"
            outcome = {
                "outcome_revealed_at_utc": "2026-08-01T00:00:00Z",
                "market_returns_1d": {"AAA": 0.01, "BBB": -0.01},
                "market_returns_5d": {"AAA": 0.02, "BBB": -0.02},
                "market_returns_20d": {"AAA": 0.03, "BBB": -0.01},
                "market_returns_60d": {"AAA": 0.04, "BBB": 0.00},
                "benchmark_returns": {
                    "1d": 0.0,
                    "5d": 0.0,
                    "20d": 0.01,
                    "60d": 0.02,
                },
                "after_cost_abnormal_returns": {
                    "AAA_5d": 0.018,
                    "BBB_5d": 0.018,
                },
                "operating_performance_changes": {
                    "AAA": "improved",
                    "BBB": "unchanged",
                },
                "post_outcome_evidence_records": [
                    self.evidence_record(
                        contradictory_id,
                        source_type="niche_news",
                        stance="contradicts",
                        temporal_role="post_outcome_reveal",
                        published_at="2021-01-01T00:00:00Z",
                        available_before_memo_seal=False,
                        affected_claims=[
                            "beneficiary mapping",
                            "implementation timing",
                        ],
                    )
                ],
                "research_assistance_records": [],
                "contradictory_evidence_review": {
                    "review_completed_at_utc": "2026-08-01T00:00:00Z",
                    "search_scope": [
                        "mainstream reporting",
                        "trade publications",
                        "niche industry reporting",
                        "company disclosures",
                    ],
                    "contradictory_evidence_ids": [contradictory_id],
                    "mixed_evidence_ids": [],
                    "late_discovered_pre_cutoff_evidence_ids": [],
                    "no_contradictory_evidence_found": False,
                    "reviewer_notes": "The niche article challenges the original beneficiary and timing claims.",
                },
                "implementation_timeline": "Implemented within one year.",
                "competing_market_explanations": ["sector rally"],
            }
            self.rehash(outcome, "outcome_packet_hash")
            case["outcome_packet"] = outcome
        return case


if __name__ == "__main__":
    unittest.main()
