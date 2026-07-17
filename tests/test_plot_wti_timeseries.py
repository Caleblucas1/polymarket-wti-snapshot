import tempfile
import unittest
from pathlib import Path

from plot_wti_timeseries import latest_window, load_snapshot


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


if __name__ == "__main__":
    unittest.main()
