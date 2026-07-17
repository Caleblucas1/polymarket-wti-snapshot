import tempfile
import unittest
from pathlib import Path

from plot_wti_timeseries import load_snapshot


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


if __name__ == "__main__":
    unittest.main()
