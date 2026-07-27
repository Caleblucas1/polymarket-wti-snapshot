import tempfile
import unittest
from pathlib import Path

from plot_wti_timeseries import (
    carry_forward_resolved_series,
    create_chart,
    latest_window,
    load_closed_market_labels,
    load_ranges,
    load_snapshot,
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

    def test_each_selector_replaces_the_single_visible_trace(self):
        figure = create_chart(
            ["2026-07-26", "2026-07-27"],
            {
                "↑ $130": [0.2, 0.1],
                "↑ $90": [100.0, 100.0],
                "↑ $80": [100.0, 100.0],
            },
        )

        self.assertEqual(len(figure.data), 1)
        buttons = figure.layout.updatemenus[0].buttons
        selected = {
            button.label: list(button.args[0]["y"][0])
            for button in buttons
        }
        self.assertEqual(selected["↑ $130"], [0.2, 0.1])
        self.assertEqual(selected["↑ $90"], [100.0, 100.0])
        self.assertEqual(selected["↑ $80"], [100.0, 100.0])

    def test_carries_forward_only_resolved_terminal_series(self):
        series, carried = carry_forward_resolved_series(
            {
                "↑ $80": [40.0, 100.0, None, None],
                "↑ $130": [1.2, 0.9, None, None],
            },
            {"↑ $80"},
        )

        self.assertEqual(series["↑ $80"], [40.0, 100.0, 100.0, 100.0])
        self.assertEqual(carried["↑ $80"], [False, False, True, True])
        self.assertEqual(series["↑ $130"], [1.2, 0.9, None, None])

    def test_loads_closed_resolved_labels_for_one_event(self):
        content = (
            "Event Key,Market,Current Status,Closed\n"
            "wti-july,↑ $80,resolved,true\n"
            "wti-july,↑ $130,,false\n"
            "other,↑ $80,resolved,true\n"
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "status.csv"
            path.write_text(content, encoding="utf-8")
            labels = load_closed_market_labels(path, event_key="wti-july")

        self.assertEqual(labels, {"↑ $80"})

    def test_marks_first_up_90_yes_satisfaction(self):
        satisfaction_at = "2026-07-23T05:15:07-04:00"
        figure = create_chart(
            ["2026-07-22", "2026-07-23", "2026-07-24"],
            {"↑ $90": [69.3, 100.0, 100.0]},
            satisfaction_at=satisfaction_at,
        )

        self.assertEqual(len(figure.layout.shapes), 1)
        marker = figure.layout.shapes[0]
        self.assertEqual(marker.x0, satisfaction_at)
        self.assertEqual(marker.x1, satisfaction_at)
        self.assertEqual(marker.line.color, "#DC2626")
        self.assertEqual(marker.line.dash, "dash")
        self.assertTrue(
            any(
                "First ↑ $90 Yes satisfied" in annotation.text
                for annotation in figure.layout.annotations
            )
        )

    def test_omits_satisfaction_marker_outside_chart_window(self):
        figure = create_chart(
            ["2026-07-24", "2026-07-25"],
            {"↑ $90": [100.0, 100.0]},
            satisfaction_at="2026-07-23T05:15:07-04:00",
        )

        self.assertEqual(len(figure.layout.shapes), 0)


if __name__ == "__main__":
    unittest.main()
