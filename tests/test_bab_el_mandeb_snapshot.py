import argparse
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from polymarket_deadline_snapshot import (
    create_heatmap_chart,
    create_line_chart,
    deadline_sort_key,
    selected_markets,
    run_tracker,
    write_deadline_chart,
)


class BabElMandebSnapshotTests(unittest.TestCase):
    def test_excludes_closed_deadlines_by_default(self):
        markets = [
            {"groupItemTitle": "June 30", "closed": True},
            {"groupItemTitle": "July 31", "closed": False},
            {"groupItemTitle": "August 31"},
        ]
        self.assertEqual(
            [market["groupItemTitle"] for market in selected_markets(markets)],
            ["July 31", "August 31"],
        )
        self.assertEqual(len(selected_markets(markets, include_closed=True)), 3)

    def test_orders_deadlines_by_calendar_date(self):
        labels = ["December 31", "July 31", "September 30", "August 31"]
        self.assertEqual(
            sorted(labels, key=deadline_sort_key),
            ["July 31", "August 31", "September 30", "December 31"],
        )

    def test_keeps_closed_deadlines_visible_when_they_are_stored(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            input_path = Path(temp_directory) / "snapshot.csv"
            input_path.write_text(
                "Deadline,2026-07-16,2026-07-17\n"
                "July 16,80.0,\n"
                "July 17,60.0,95.3\n"
                "July 18,30.0,40.0\n",
                encoding="utf-8",
            )
            count = write_deadline_chart(
                input_path,
                Path(temp_directory) / "chart.html",
                days=7,
                title="Iran action",
            )
        self.assertEqual(count, 3)

    def test_line_chart_uses_asymmetric_range_whiskers(self):
        figure = create_line_chart(
            ["2026-07-17"],
            {"July 17": [50.0]},
            "Example",
            ranges={"July 17": {"2026-07-17": (20.0, 80.0)}},
        )
        self.assertEqual(list(figure.data[0].error_y.arrayminus), [30.0])
        self.assertEqual(list(figure.data[0].error_y.array), [30.0])

    def test_dense_heatmap_shows_intraday_range(self):
        series = {f"July {day}": [50.0] for day in range(1, 10)}
        ranges = {
            label: {"2026-07-17": (20.0, 80.0)}
            for label in series
        }
        figure = create_heatmap_chart(
            ["2026-07-17"], series, "Example", ranges=ranges
        )
        self.assertIn("↕ 20.0–80.0", figure.data[0].text[0][0])

    def test_backfills_ranges_for_closed_and_open_stored_deadlines(self):
        target = datetime(2026, 7, 17, 9, tzinfo=ZoneInfo("America/New_York"))
        markets = [
            {"groupItemTitle": "July 16", "closed": True},
            {"groupItemTitle": "July 18", "closed": False},
        ]
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "snapshot.csv"
            range_output = Path(temp_directory) / "ranges.csv"
            output.write_text(
                "Deadline,2026-07-17\nJuly 16,90.0\nJuly 18,40.0\n",
                encoding="utf-8",
            )
            original = output.read_bytes()
            args = argparse.Namespace(
                output=output,
                range_output=range_output,
                chart_output=Path(temp_directory) / "chart.html",
                slug="event",
                title="Event",
                days=7,
                hour=9,
                timeout=5,
                no_chart=True,
                include_closed=False,
            )
            range_rows = [
                {"Deadline": "July 16", "Date": "2026-07-17", "Low": 90.0, "High": 90.0},
                {"Deadline": "July 18", "Date": "2026-07-17", "Low": 20.0, "High": 60.0},
            ]
            with (
                patch("polymarket_deadline_snapshot.snapshot_targets", return_value=[target]),
                patch("polymarket_deadline_snapshot.build_session", return_value=object()),
                patch(
                    "polymarket_deadline_snapshot.fetch_event",
                    return_value={"title": "Event", "markets": markets},
                ),
                patch(
                    "polymarket_deadline_snapshot.collect_rows_and_ranges",
                    return_value=([], range_rows),
                ) as collect,
            ):
                result = run_tracker(args)

            self.assertEqual(result.status, "current")
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(len(range_output.read_text(encoding="utf-8").splitlines()), 3)
            self.assertEqual(len(collect.call_args.args[1]), 2)

    def test_closed_event_backfills_latest_stored_dates(self):
        requested = datetime(2026, 7, 18, 9, tzinfo=ZoneInfo("America/New_York"))
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "snapshot.csv"
            output.write_text(
                "Deadline,2026-07-11\nJuly 11,90.0\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                output=output,
                range_output=Path(temp_directory) / "ranges.csv",
                chart_output=Path(temp_directory) / "chart.html",
                slug="event",
                title="Event",
                days=7,
                hour=9,
                timeout=5,
                no_chart=True,
                include_closed=False,
            )
            with (
                patch("polymarket_deadline_snapshot.snapshot_targets", return_value=[requested]),
                patch("polymarket_deadline_snapshot.build_session", return_value=object()),
                patch(
                    "polymarket_deadline_snapshot.fetch_event",
                    return_value={
                        "markets": [{"groupItemTitle": "July 11", "closed": True}]
                    },
                ),
                patch(
                    "polymarket_deadline_snapshot.collect_rows_and_ranges",
                    return_value=(
                        [],
                        [
                            {
                                "Deadline": "July 11",
                                "Date": "2026-07-11",
                                "Low": 90.0,
                                "High": 90.0,
                            }
                        ],
                    ),
                ) as collect,
            ):
                result = run_tracker(args)

            self.assertEqual(result.status, "closed")
            collected_target = collect.call_args.args[2][0]
            self.assertEqual(collected_target.date().isoformat(), "2026-07-11")


if __name__ == "__main__":
    unittest.main()
