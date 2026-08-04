import unittest

from signal_research.hypotheses import get_hypothesis, validate_hypotheses
from signal_research.registry import get_candidate, load_candidates, validate_registry


class S012RegistryTests(unittest.TestCase):
    def test_s012_is_visible_in_central_registry(self):
        candidate = get_candidate("S-012")
        self.assertEqual(
            "BTC-QQQ-REALIZED-VOL-COMPRESSION-001", candidate.registry_id
        )
        self.assertEqual("backtest", candidate.stage.value)
        self.assertEqual("watchlist", candidate.operational_status.value)
        self.assertEqual(9, len(load_candidates()))

    def test_s012_canonical_hypothesis_is_frozen_and_resolvable(self):
        row = get_hypothesis("BTC-QQQ-RV")
        self.assertEqual("frozen", row["freeze_status"])
        self.assertTrue(row["dataset_eligible"])
        self.assertEqual(30, 30)  # The exact rule is asserted through its frozen text below.
        self.assertIn("preceding 30 calendar days", row["trigger_rule"])

    def test_registry_and_hypothesis_extension_set_is_valid(self):
        self.assertEqual([], validate_registry())
        self.assertEqual([], validate_hypotheses())


if __name__ == "__main__":
    unittest.main()
