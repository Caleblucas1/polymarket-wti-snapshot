import contextlib
import io
import json
import unittest
from pathlib import Path

from narrative_break_signal import (
    Level,
    PRECLASSIFIED_SCENARIOS,
    classify_scenario,
    main,
)


class NarrativeBreakSignalTests(unittest.TestCase):
    def test_signal_market_catalog_has_unique_urls_and_five_variables(self):
        catalog = json.loads(Path("signal_market_catalog.json").read_text(encoding="utf-8"))
        urls = [event["url"] for event in catalog["events"].values()]

        self.assertEqual(len(catalog["variables"]), 5)
        self.assertEqual(len(urls), 16)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(
            [variable["key"] for variable in catalog["variables"]],
            [
                "diplomacy",
                "blockade_near_term",
                "blockade_long_term",
                "shipping_disruption",
                "oil_upside",
            ],
        )

    def test_batch_questionnaire_contains_all_scenarios_and_readable_headers(self):
        questionnaire = Path("signal_questionnaire.html").read_text(encoding="utf-8")

        self.assertIn("U.S.–Iran diplomacy and de-escalation odds", questionnaire)
        self.assertIn("Iranian blockade ends by near-term deadline", questionnaire)
        self.assertIn("Hormuz and regional shipping-disruption odds", questionnaire)
        self.assertIn("WTI and crude-oil upside-threshold odds", questionnaire)
        self.assertIn("for (let i = 0; i < 32; i += 1)", questionnaire)
        self.assertIn("grayCode(index) ^ 0b11100", questionnaire)
        self.assertIn("Copy completed answers for ChatGPT", questionnaire)

    def test_peace_drop_alone_is_weaker_yellow_when_curve_does_not_confirm(self):
        result = classify_scenario(
            {
                "peace_talk_near_term": "down",
                "peace_talk_long_term": "stable",
                "blockade_near_term": "stable",
                "blockade_long_term": "stable",
                "shipping_risk": "flat",
                "wti_upside_threshold": "flat",
            }
        )

        self.assertEqual(result.level, Level.WEAKER_YELLOW)
        self.assertIn("near-term blockade odds did not fall", " ".join(result.matched_rules))

    def test_question_two_calibration_moves_toward_yellow_orange(self):
        result = classify_scenario(
            {
                "peace_talk_near_term": "down",
                "peace_talk_long_term": "stable",
                "blockade_near_term": "down",
                "blockade_long_term": "stable",
                "shipping_risk": "flat",
                "wti_upside_threshold": "slightly_up",
            }
        )

        self.assertEqual(result.level, Level.YELLOW_ORANGE)
        self.assertIn("calibrated Question 2 rule", " ".join(result.matched_rules))
        self.assertIn("unmodeled-shock risk", " ".join(result.matched_rules))

    def test_near_term_drop_with_shipping_and_wti_confirmation_is_stronger(self):
        result = classify_scenario(
            {
                "peace_talk_near_term": "down",
                "blockade_near_term": "down",
                "blockade_long_term": "stable",
                "shipping_risk": "up",
                "hormuz_normalization": "down",
                "wti_upside_threshold": "up",
            }
        )

        self.assertIn(result.level, {Level.YELLOW_ORANGE, Level.ORANGE, Level.RED})
        self.assertGreaterEqual(result.score, 7)

    def test_full_curve_drop_with_physical_confirmation_is_red(self):
        result = classify_scenario(
            {
                "peace_talk_near_term": "hard_down",
                "peace_talk_long_term": "down",
                "blockade_near_term": "hard_down",
                "blockade_intermediate": "down",
                "blockade_long_term": "down",
                "shipping_risk": "up",
                "hormuz_normalization": "down",
                "wti_upside_threshold": "up",
            }
        )

        self.assertEqual(result.level, Level.RED)

    def test_preclassified_scenarios_match_expected_levels(self):
        for card in PRECLASSIFIED_SCENARIOS:
            with self.subTest(card=card.key):
                result = classify_scenario(card.scenario)
                self.assertEqual(result.level, card.expected_level)

    def test_cli_lists_preclassified_scenarios(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--list-scenarios"])

        self.assertEqual(exit_code, 0)
        self.assertIn("question-2", output.getvalue())
        self.assertIn("Pre-classified scenario cards", output.getvalue())

    def test_cli_classifies_prebuilt_scenario(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--scenario", "question-2"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Expected: Yellow/Orange", output.getvalue())
        self.assertIn("Classified: Yellow/Orange", output.getvalue())


if __name__ == "__main__":
    unittest.main()
