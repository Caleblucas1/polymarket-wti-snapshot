import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from polymarket_resolution_status import (
    merge_status_rows,
    status_rows,
    write_status_csv,
)


class ResolutionStatusTests(unittest.TestCase):
    def test_detects_current_and_historical_disputes(self):
        event = {
            "title": "Iran action",
            "markets": [
                {
                    "groupItemTitle": "July 9",
                    "conditionId": "past",
                    "umaResolutionStatus": "resolved",
                    "umaResolutionStatuses": '["proposed", "disputed", "proposed"]',
                    "closed": True,
                },
                {
                    "groupItemTitle": "July 17",
                    "conditionId": "current",
                    "umaResolutionStatus": "disputed",
                    "umaResolutionStatuses": ["proposed", "disputed"],
                },
            ],
        }
        rows = status_rows(
            "iran",
            "Configured title",
            event,
            checked_at=datetime(2026, 7, 18, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(rows[0]["Currently Disputed"], "false")
        self.assertEqual(rows[0]["Ever Disputed"], "true")
        self.assertEqual(rows[1]["Currently Disputed"], "true")
        self.assertEqual(rows[1]["Dispute Count"], "1")

    def test_past_dispute_flag_is_sticky_after_metadata_changes(self):
        existing = {
            "Event Key": "iran",
            "Market": "July 9",
            "Condition ID": "condition",
            "Ever Disputed": "true",
            "Dispute Count": "2",
            "Status History": "proposed > disputed > proposed > disputed",
            "First Seen": "first",
        }
        incoming = {
            **existing,
            "Ever Disputed": "false",
            "Dispute Count": "0",
            "Status History": "proposed",
            "First Seen": "later",
            "Last Checked": "now",
        }
        merged = merge_status_rows([existing], [incoming])[0]
        self.assertEqual(merged["Ever Disputed"], "true")
        self.assertEqual(merged["Dispute Count"], "2")
        self.assertEqual(merged["First Seen"], "first")

    def test_status_csv_preserves_existing_markets_not_in_latest_response(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "status.csv"
            row = status_rows(
                "event",
                "Title",
                {"markets": [{"groupItemTitle": "July 17", "conditionId": "id"}]},
                checked_at=datetime(2026, 7, 18, tzinfo=ZoneInfo("UTC")),
            )[0]
            write_status_csv(path, [row])
            _, count = write_status_csv(path, [])
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
