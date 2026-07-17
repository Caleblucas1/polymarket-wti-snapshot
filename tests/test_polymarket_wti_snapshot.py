import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from polymarket_wti_snapshot import (
    prices_at_or_before,
    merge_and_write_csv,
    snapshot_targets,
    yes_token_id,
)


class SnapshotTests(unittest.TestCase):
    def test_uses_previous_day_before_snapshot_hour(self):
        now = datetime(2026, 7, 17, 8, 30, tzinfo=ZoneInfo("America/New_York"))
        targets = snapshot_targets(now, days=3)
        self.assertEqual(
            [target.isoformat() for target in targets],
            [
                "2026-07-14T09:00:00-04:00",
                "2026-07-15T09:00:00-04:00",
                "2026-07-16T09:00:00-04:00",
            ],
        )

    def test_includes_today_after_snapshot_hour(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(snapshot_targets(now, days=1)[0].date().isoformat(), "2026-07-17")

    def test_handles_daylight_saving_offset_per_date(self):
        now = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        targets = snapshot_targets(now, days=3)
        self.assertEqual([target.utcoffset().total_seconds() for target in targets], [-14400, -18000, -18000])

    def test_finds_yes_token_by_outcome_name(self):
        market = {"outcomes": '["No", "Yes"]', "clobTokenIds": '["no-id", "yes-id"]'}
        self.assertEqual(yes_token_id(market), "yes-id")

    def test_falls_back_to_first_token(self):
        self.assertEqual(yes_token_id({"clobTokenIds": ["first", "second"]}), "first")

    def test_selects_latest_price_at_or_before_target(self):
        targets = [
            datetime.fromtimestamp(200, tz=ZoneInfo("UTC")),
            datetime.fromtimestamp(350, tz=ZoneInfo("UTC")),
        ]
        history = [{"t": 300, "p": 0.3}, {"t": 100, "p": 0.1}, {"bad": "row"}]
        self.assertEqual(prices_at_or_before(history, targets), [0.1, 0.3])

    def test_appends_only_missing_dates(self):
        targets = [
            datetime(2026, 7, 16, 9, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 7, 17, 9, tzinfo=ZoneInfo("America/New_York")),
        ]
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "snapshot.csv"
            path.write_text(
                "Price Bin,2026-07-15,2026-07-16\n↑ $90,20.0,22.0\n",
                encoding="utf-8",
            )
            added, row_count = merge_and_write_csv(
                path,
                [{"Price Bin": "↑ $90", "2026-07-16": 99.0, "2026-07-17": 25.0}],
                targets,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual((added, row_count), (1, 1))
        self.assertIn("2026-07-15,2026-07-16,2026-07-17", content)
        self.assertIn("↑ $90,20.0,22.0,25.0", content)
        self.assertNotIn("99.0", content)


if __name__ == "__main__":
    unittest.main()
