import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from polymarket_resolution_status import (
    append_resolution_events,
    bootstrap_current_dispute_events,
    merge_status_rows,
    resolution_transition_events,
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

    def test_records_terminal_yes_probability(self):
        rows = status_rows(
            "event",
            "Title",
            {
                "markets": [
                    {
                        "groupItemTitle": "July 31",
                        "conditionId": "condition",
                        "umaResolutionStatus": "resolved",
                        "closed": True,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["1", "0"]',
                    }
                ]
            },
            checked_at=datetime(2026, 7, 27, tzinfo=ZoneInfo("UTC")),
        )

        self.assertEqual(rows[0]["Resolved Outcome"], "Yes")
        self.assertEqual(rows[0]["Yes Resolution Probability"], "100.0")

    def test_emits_dispute_and_resolution_transitions(self):
        existing = {
            "Event Key": "iran",
            "Event Title": "Iran",
            "Market": "July 23",
            "Condition ID": "condition",
            "Current Status": "proposed",
            "Dispute Count": "0",
        }
        disputed = {
            **existing,
            "Current Status": "disputed",
            "Dispute Count": "1",
        }
        observed_at = datetime(2026, 7, 27, 13, tzinfo=ZoneInfo("UTC"))
        events = resolution_transition_events(
            [existing],
            [disputed],
            observed_at=observed_at,
        )
        self.assertEqual(events[0]["Event Type"], "dispute-detected")

        resolved = {
            **disputed,
            "Current Status": "resolved",
        }
        events = resolution_transition_events(
            [disputed],
            [resolved],
            observed_at=observed_at,
        )
        self.assertEqual(events[0]["Event Type"], "resolved")

    def test_bootstraps_and_preserves_current_dispute_event(self):
        row = {
            "Event Key": "iran",
            "Event Title": "Iran",
            "Market": "July 23",
            "Condition ID": "condition",
            "Currently Disputed": "true",
            "Dispute Count": "2",
            "Last Checked": "2026-07-27T09:31:20-04:00",
        }
        events = bootstrap_current_dispute_events([row])
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "events.csv"
            first = append_resolution_events(path, events)
            second = append_resolution_events(path, events)

        self.assertEqual(first, (1, 1))
        self.assertEqual(second, (0, 1))

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
