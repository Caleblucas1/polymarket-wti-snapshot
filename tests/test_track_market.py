import unittest

from track_market import load_registry
from update_all_markets import build_parser


class EventRegistryTests(unittest.TestCase):
    def test_daily_updater_includes_every_configured_market(self):
        registry = load_registry()
        args = build_parser().parse_args([])
        self.assertEqual(set(args.events), set(registry))
        self.assertEqual(len(args.events), 7)


if __name__ == "__main__":
    unittest.main()
