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
    satisfaction_events,
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

    def test_uses_single_condition_dropdown_chart(self):
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
        self.assertEqual({trace.xaxis for trace in figure.data}, {None})
        self.assertEqual([trace.visible for trace in figure.data].count(True), 1)
        self.assertFalse(figure.layout.showlegend)
        self.assertEqual(figure.layout.updatemenus[0].buttons[0].label, "↓ $50")

    def test_chart_keeps_each_price_bin_bound_to_its_own_values(self):
        source = {
            "↑ $80": [100.0, 100.0, None],
            "↑ $85": [65.0, None, 12.5],
            "↑ $90": [38.3, 69.3, None],
            "↑ $130": [0.7, 0.2, 0.1],
            "↓ $85": [5.0, 50.0, None],
            "↓ $90": [79.0, 87.0, 100.0],
        }
        figure = create_chart(
            ["2026-07-25", "2026-07-26", "2026-07-27"],
            source,
        )

        plotted = {trace.name: list(trace.y) for trace in figure.data}
        for label, values in source.items():
            self.assertEqual(plotted[label], values)

    def test_marks_every_yes_resolution_in_the_visible_window(self):
        eastern = ZoneInfo("America/New_York")
        conditions = [
            {
                "label": "↑ $80",
                "resolved_at": datetime(2026, 7, 21, 7, tzinfo=eastern),
                "resolved_yes": True,
            },
            {
                "label": "↑ $85",
                "resolved_at": datetime(2026, 7, 23, 6, tzinfo=eastern),
                "resolved_yes": True,
            },
            {
                "label": "↑ $90",
                "resolved_at": datetime(2026, 7, 24, 5, tzinfo=eastern),
                "resolved_yes": True,
            },
            {
                "label": "↑ $130",
                "resolved_at": None,
                "resolved_yes": False,
            },
            {
                "label": "↓ $90",
                "resolved_at": datetime(2026, 7, 18, 5, tzinfo=eastern),
                "resolved_yes": True,
            },
        ]
        figure = create_chart(
            ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"],
            {"↑ $80": [100.0, None, None, None], "↑ $90": [40.0, 60.0, None, None]},
            resolved_events=satisfaction_events(conditions),
        )

        marker_text = [
            annotation.text
            for annotation in figure.layout.annotations
            if annotation.text and annotation.text.endswith(" Yes")
        ]
        self.assertEqual(len(figure.layout.shapes), 3)
        self.assertIn("↑ $80 Yes", marker_text)
        self.assertIn("↑ $85 Yes", marker_text)
        self.assertIn("↑ $90 Yes", marker_text)
        self.assertNotIn("↓ $90 Yes", marker_text)

        resolution_traces = [
            trace for trace in figure.data if trace.name == "↑ $80 resolution"
        ]
        self.assertEqual(len(resolution_traces), 1)
        self.assertIn("Resolution method", resolution_traces[0].hovertemplate)
        self.assertNotIn("terminal", resolution_traces[0].hovertemplate.lower())

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

    def test_replacement_masking_is_per_price_bin_not_global(self):
        eastern = ZoneInfo("America/New_York")
        conditions = [
            {
                "label": "↑ $80",
                "condition_id": "up80",
                "created_at": datetime(2026, 7, 1, tzinfo=eastern),
                "resolved_at": datetime(2026, 7, 14, 10, tzinfo=eastern),
                "closed": True,
            },
            {
                "label": "↑ $90",
                "condition_id": "up90-old",
                "created_at": datetime(2026, 6, 25, tzinfo=eastern),
                "resolved_at": datetime(2026, 7, 23, 7, tzinfo=eastern),
                "closed": True,
            },
            {
                "label": "↑ $90",
                "condition_id": "up90-new",
                "created_at": datetime(2026, 7, 27, 12, tzinfo=eastern),
                "resolved_at": None,
                "closed": False,
            },
        ]
        masked = mask_inactive_condition_dates(
            ["2026-07-22", "2026-07-23", "2026-07-27"],
            {
                "↑ $80": [100.0, 100.0, 100.0],
                "↑ $90": [69.3, 100.0, 15.0],
                "↑ $130": [0.6, 0.4, 0.1],
            },
            conditions,
        )

        self.assertEqual(masked["↑ $80"], [None, None, None])
        self.assertEqual(masked["↑ $90"], [69.3, None, None])
        self.assertEqual(masked["↑ $130"], [0.6, 0.4, 0.1])

    def test_latest_active_replacement_is_selected_per_price_bin(self):
        eastern = ZoneInfo("America/New_York")
        conditions = [
            {
                "label": "↑ $90",
                "condition_id": "older-active",
                "created_at": datetime(2026, 7, 24, 12, tzinfo=eastern),
                "resolved_at": None,
                "last_checked": datetime(2026, 7, 27, 15, tzinfo=eastern),
                "closed": False,
                "current_probability": 22.0,
            },
            {
                "label": "↑ $90",
                "condition_id": "newest-active",
                "created_at": datetime(2026, 7, 27, 12, tzinfo=eastern),
                "resolved_at": None,
                "last_checked": datetime(2026, 7, 27, 16, tzinfo=eastern),
                "closed": False,
                "current_probability": 15.0,
            },
            {
                "label": "↑ $85",
                "condition_id": "up85-active",
                "created_at": datetime(2026, 7, 26, 12, tzinfo=eastern),
                "resolved_at": None,
                "last_checked": datetime(2026, 7, 27, 16, tzinfo=eastern),
                "closed": False,
                "current_probability": 35.0,
            },
        ]

        active = latest_active_points(conditions)

        self.assertEqual(active["↑ $90"][1], 15.0)
        self.assertEqual(active["↑ $85"][1], 35.0)


if __name__ == "__main__":
    unittest.main()
