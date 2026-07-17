import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from polymarket_wti_snapshot import (
    prices_at_or_before,
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


if __name__ == "__main__":
    unittest.main()
