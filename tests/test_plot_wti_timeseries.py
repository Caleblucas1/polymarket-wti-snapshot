import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from plot_wti_timeseries import (
    create_chart,
    latest_active_points,
    latest_window,
    load_ranges,
    load_snapshot,
    mask_inactive_condition_dates,
)


class TimeSeriesDataTests(unittest.TestCase):
    def test_loads_snapshot_series(self):
        content = (
            "Price Bin,2026-07-16,2026-07-17\n"
            "↑ $100,6.2,8.1\n"
            "↓ $60,1.5,1.1\n"
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "snapshot.csv"
            path.write_text(content, encoding="utf-8")
            dates, series = load_snapshot(path)

        self.assertEqual(dates, ["2026-07-16", "2026-07-17"])
        self.assertEqual(series["↑ $100"], [6.2, 8.1])
        self.assertEqual(series["↓ $60"], [1.5, 1.1])

    def test_allows_missing_value(self):
        content = "Price Bin,2026-07-17\n↑ $100,\n"
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "snapshot.csv"
            path.write_text(content, encoding="utf-8")
            _, series = load_snapshot(path)
        self.assertEqual(series["↑ $100"], [None])

    def test_rejects_out_of_range_percentage(self):
        content = "Price Bin,2026-07-17\n↑ $100,101\n"
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "snapshot.csv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside 0-100"):
                load_snapshot(path)

    def test_selects_latest_seven_dates(self):
        dates = [f"2026-07-{day:02d}" for day in range(1, 11)]
        series = {"↑ $90": [float(day) for day in range(1, 11)]}
        selected_dates, selected_series = latest_window(dates, series)
        self.assertEqual(selected_dates[0], "2026-07-04")
        self.assertEqual(selected_dates[-1], "2026-07-10")
        self.assertEqual(selected_series["↑ $90"], [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])

    def test_loads_range_series(self):
        content = (
            "Price Bin,Date,Low,High\n"
            "↑ $90,2026-07-16,20.0,30.0\n"
            "↑ $90,2026-07-17,22.0,40.0\n"
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "ranges.csv"
            path.write_text(content, encoding="utf-8")
            ranges = load_ranges(path)

        self.assertEqual(ranges["↑ $90"]["2026-07-17"], (22.0, 40.0))

    def test_adds_asymmetric_whiskers_to_snapshot_points(self):
        figure = create_chart(
            ["2026-07-16", "2026-07-17"],
            {"↑ $90": [25.0, 30.0]},
            ranges={
                "↑ $90": {
                    "2026-07-16": (20.0, 28.0),
                    "2026-07-17": (22.0, 40.0),
                }
            },
        )
        trace = figure.data[0]

        self.assertEqual(list(trace.error_y.arrayminus), [5.0, 8.0])
        self.assertEqual(list(trace.error_y.array), [3.0, 10.0])
        self.assertTrue(trace.error_y.visible)

    def test_splits_price_bins_into_two_visible_panels(self):
        figure = create_chart(
            ["2026-07-26", "2026-07-27"],
            {
                "↓ $50": [1.0, 2.0],
                "↑ $80": [20.0, 30.0],
                "↑ $90": [40.0, 50.0],
                "↑ $130": [1.0, 1.0],
            },
        )

        self.assertEqual(len(figure.data), 4)
        self.assertEqual({trace.xaxis for trace in figure.data}, {"x", "x2"})
        self.assertTrue(all(trace.visible is None for trace in figure.data))

    def test_masks_resolved_gap_and_uses_latest_active_replacement(self):
        eastern = ZoneInfo("America/New_York")
        conditions = [
            {
                "label": "↑ $90",
                "condition_id": "old",
                "created_at": datetime(2026, 6, 25, tzinfo=eastern),
                "resolved_at": datetime(2026, 7, 23, 7, 17, tzinfo=eastern),
                "last_checked": datetime(2026, 7, 23, 9, tzinfo=eastern),
                "closed": True,
                "resolved_yes": True,
                "current_probability": 100.0,
            },
            {
                "label": "↑ $90",
                "condition_id": "new",
                "created_at": datetime(2026, 7, 27, 12, 27, tzinfo=eastern),
                "resolved_at": None,
                "last_checked": datetime(2026, 7, 27, 16, 15, tzinfo=eastern),
                "closed": False,
                "resolved_yes": False,
                "current_probability": 15.0,
            },
        ]
        masked = mask_inactive_condition_dates(
            ["2026-07-22", "2026-07-23", "2026-07-27"],
            {"↑ $90": [69.3, 100.0, 100.0]},
            conditions,
        )

        self.assertEqual(masked["↑ $90"], [69.3, None, None])
        self.assertEqual(
            latest_active_points(conditions)["↑ $90"][1],
            15.0,
        )


if __name__ == "__main__":
    unittest.main()
