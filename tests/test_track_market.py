import unittest

from track_market import load_registry


class EventRegistryTests(unittest.TestCase):
    def test_daily_registry_contains_the_four_persistent_automation_files(self):
        registry = load_registry()
        daily_events = {key for key, config in registry.items() if config["daily"]}
        self.assertEqual(
            daily_events,
            {"wti-july", "houthi-saudi", "crude-oil-ath", "wti-week-july-13"},
        )


if __name__ == "__main__":
    unittest.main()
