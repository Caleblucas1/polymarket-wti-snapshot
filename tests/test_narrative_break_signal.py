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
    def test_signal_market_catalog_has_unique_urls_and_five_market_level_variables(self):
        catalog = json.loads(Path("signal_market_catalog.json").read_text(encoding="utf-8"))
        urls = [event["url"] for event in catalog["events"].values()]

        self.assertEqual(len(catalog["variables"]), 5)
        self.assertEqual(len(urls), 17)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(catalog["version"], 3)
        self.assertEqual(catalog["events"]["wti_july_2026"]["recurrence"]["frequency"], "monthly")
        self.assertEqual(catalog["events"]["hormuz_transit_july_20"]["recurrence"]["frequency"], "weekly")
        self.assertTrue(catalog["events"]["hormuz_transit_july_27"]["historical_only"])
        self.assertIn(
            "https://polymarket.com/event/"
            "houthis-successfully-target-shipping-onptptpt-20260722225036915",
            urls,
        )
        self.assertEqual(
            [variable["key"] for variable in catalog["variables"]],
            [
                "peace_talks_aug_31",
                "blockade_near_term",
                "blockade_long_term",
                "bab_el_mandeb_closed_aug_31",
                "wti_100_july",
            ],
        )

    def test_batch_questionnaire_contains_all_scenarios_and_readable_headers(self):
        questionnaire = Path("signal_questionnaire.html").read_text(encoding="utf-8")

        self.assertIn("Next U.S.–Iran peace talks by Aug. 31", questionnaire)
        self.assertIn("end of Iranian blockade by Aug. 31", questionnaire)
        self.assertIn("Bab el-Mandeb effectively closed by Aug. 31", questionnaire)
        self.assertIn("WTI hits $100 in July 2026", questionnaire)
        self.assertIn('"Flat"', questionnaire)
        self.assertIn("priorityOnly", questionnaire)
        self.assertIn("for (let i = 0; i < 32; i += 1)", questionnaire)
        self.assertIn("grayCode(index) ^ 0b11100", questionnaire)
        self.assertIn("Copy completed answers for ChatGPT", questionnaire)
        catalog = json.loads(Path("signal_market_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(
            catalog["events"]["houthis_target_shipping_july_22"]["question_structure"],
            "Each conditional asks whether a qualifying incident occurs on one exact calendar date.",
        )

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
