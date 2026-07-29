import contextlib
import io
import unittest

from narrative_break_signal import (
    Level,
    PRECLASSIFIED_SCENARIOS,
    classify_scenario,
    main,
)


class NarrativeBreakSignalTests(unittest.TestCase):
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

    def test_question_two_calibration_is_yellow(self):
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

        self.assertEqual(result.level, Level.YELLOW)
        self.assertIn("calibrated Question 2 rule", " ".join(result.matched_rules))

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
        self.assertIn("Expected: Yellow", output.getvalue())
        self.assertIn("Classified: Yellow", output.getvalue())


if __name__ == "__main__":
    unittest.main()
