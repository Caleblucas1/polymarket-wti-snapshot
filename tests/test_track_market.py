import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from polymarket_wti_snapshot import TrackerResult
from track_market import load_registry
from update_all_markets import build_parser, main


class EventRegistryTests(unittest.TestCase):
    def test_daily_updater_includes_every_configured_market(self):
        registry = load_registry()
        args = build_parser().parse_args([])
        self.assertEqual(set(args.events), set(registry))
        self.assertEqual(len(args.events), 7)
        self.assertTrue(all(config.get("range_output") for config in registry.values()))

    def test_reports_precise_aggregate_statuses(self):
        args = SimpleNamespace(
            workers=4,
            events=["append", "current", "closed", "broken"],
            data_dir=".",
            days=7,
            hour=9,
            timeout=5,
            with_charts=False,
        )
        results = {
            "append": TrackerResult("appended", added_dates=1),
            "current": TrackerResult("current"),
            "closed": TrackerResult("closed"),
            "broken": TrackerResult("failed", exit_code=1),
        }
        parser = Mock()
        parser.parse_args.return_value = args
        output = io.StringIO()
        with (
            patch("update_all_markets.build_parser", return_value=parser),
            patch("update_all_markets.run_event", side_effect=lambda key, **_: results[key]),
            patch(
                "update_all_markets.load_registry",
                return_value={key: {} for key in args.events},
            ),
            patch(
                "update_all_markets.refresh_resolution_status",
                return_value=(2, 10, []),
            ),
            redirect_stdout(output),
        ):
            exit_code = main()

        self.assertEqual(exit_code, 1)
        self.assertIn("append: appended 1 date(s)", output.getvalue())
        self.assertIn("current: already current", output.getvalue())
        self.assertIn("closed: fully closed", output.getvalue())
        self.assertIn("broken: failed", output.getvalue())
        self.assertIn("resolution-status: refreshed 10 markets", output.getvalue())


if __name__ == "__main__":
    unittest.main()
