import unittest

from signal_research.policy_benchmark import interpretation_score, investment_score, load_protocol
from signal_research.policy_pilots import get_pilot, summarize_pilots, validate_pilots
from signal_research.policy_roadmap import historical_readiness


CASE_ID = "POLICY-PILOT-CHIPS-INTC-2022"


class PolicyPilotTests(unittest.TestCase):
    def test_committed_pilot_is_valid(self):
        self.assertEqual([], validate_pilots())
        summary = summarize_pilots()
        self.assertTrue(summary["valid"])
        self.assertEqual(1, summary["cases"])
        self.assertEqual(1, summary["scored_cases"])
        self.assertEqual({"scored": 1}, summary["stage_counts"])
        self.assertEqual(0, summary["readiness_eligible_cases"])
        self.assertFalse(summary["readiness_eligible"])
        self.assertFalse(summary["real_money_trading_authorized"])

    def test_case_preserves_the_no_trade_decision(self):
        case = get_pilot(CASE_ID)
        self.assertEqual("scored", case["stage"])
        self.assertFalse(case["readiness_eligible"])
        self.assertTrue(case["known_outcome_contamination"])
        self.assertEqual(
            "no_trade",
            case["sealed_memo"]["expected_direction"]["canonical_five_session_trade"],
        )
        self.assertEqual(
            "no_trade",
            case["pipeline_result"]["canonical_trade_result"],
        )
        self.assertFalse(
            case["outcome_packet"]["after_cost_abnormal_returns"]["trade_executed"]
        )
        self.assertEqual(0, case["pipeline_result"]["readiness_credit"])
        self.assertEqual("none", case["pipeline_result"]["capital_rights_change"])

    def test_scores_remain_separate_and_honest(self):
        case = get_pilot(CASE_ID)
        protocol = load_protocol()
        self.assertEqual(90.0, interpretation_score(case, protocol))
        self.assertEqual(50.0, investment_score(case, protocol))
        self.assertGreater(
            interpretation_score(case, protocol),
            investment_score(case, protocol),
        )
        self.assertFalse(
            case["outcome_packet"]["benchmark_returns"]["exact_canonical_interval_available"]
        )
        self.assertTrue(
            case["outcome_packet"]["after_cost_abnormal_returns"]["diagnostic_only"]
        )

    def test_contradictory_and_mixed_evidence_are_explicit(self):
        case = get_pilot(CASE_ID)
        review = case["outcome_packet"]["contradictory_evidence_review"]
        self.assertIn(
            "POLICY-PILOT-CHIPS-INTC-2022-EVID-005",
            review["contradictory_evidence_ids"],
        )
        self.assertIn(
            "POLICY-PILOT-CHIPS-INTC-2022-EVID-007",
            review["mixed_evidence_ids"],
        )
        self.assertFalse(review["no_contradictory_evidence_found"])
        records = (
            case["input_packet"]["pre_cutoff_evidence_records"]
            + case["outcome_packet"]["post_outcome_evidence_records"]
        )
        self.assertTrue(all(record["authors"] for record in records))
        self.assertTrue(all(record["publisher"] for record in records))

    def test_no_ai_assistance_was_claimed_for_this_case(self):
        case = get_pilot(CASE_ID)
        self.assertEqual([], case["input_packet"]["research_assistance_records"])
        self.assertEqual([], case["outcome_packet"]["research_assistance_records"])

    def test_pilot_does_not_change_historical_readiness_counts(self):
        readiness = historical_readiness()
        self.assertEqual(0, readiness["selected_cases"])
        self.assertEqual(0, readiness["scored_cases"])
        self.assertFalse(readiness["passed"])


if __name__ == "__main__":
    unittest.main()
