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
                        "createdAt": "2026-07-20T16:27:00Z",
                        "closedTime": "2026-07-23 11:17:05+00",
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["1", "0"]',
                    }
                ]
            },
            checked_at=datetime(2026, 7, 27, tzinfo=ZoneInfo("UTC")),
        )

        self.assertEqual(rows[0]["Resolved Outcome"], "Yes")
        self.assertEqual(rows[0]["Yes Resolution Probability"], "100.0")
        self.assertEqual(rows[0]["Current Yes Probability"], "100.0")
        self.assertEqual(rows[0]["Condition Created At"], "2026-07-20T16:27:00Z")
        self.assertEqual(rows[0]["Resolved At"], "2026-07-23 11:17:05+00")

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
            "Resolved At": "2026-07-28T13:00:00Z",
            "Resolved Outcome": "Yes",
            "Yes Resolution Probability": "100.0",
            "Automatically Resolved": "false",
        }
        events = resolution_transition_events(
            [disputed],
            [resolved],
            observed_at=observed_at,
        )
        self.assertEqual(events[0]["Event Type"], "resolved")
        self.assertEqual(events[0]["Resolved Outcome"], "Yes")
        self.assertEqual(events[0]["Yes Resolution Probability"], "100.0")
        self.assertEqual(events[0]["Automatically Resolved"], "false")
        self.assertIn("outcome=Yes", events[0]["Resolution Details"])
        self.assertIn("yes_probability=100.0", events[0]["Resolution Details"])

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

    def test_appends_resolution_events_from_legacy_schema_with_new_details(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "events.csv"
            path.write_text(
                "Observed At,Event Key,Event Title,Market,Condition ID,Event Type,"
                "Previous Status,Current Status,Dispute Count\n"
                "2026-07-27T09:31:20-04:00,iran,Iran,July 23,old,"
                "dispute-detected,unknown,disputed,2\n",
                encoding="utf-8",
            )
            appended, total = append_resolution_events(
                path,
                [
                    {
                        "Observed At": "2026-07-28T09:00:00-04:00",
                        "Event Key": "iran",
                        "Event Title": "Iran",
                        "Market": "July 24",
                        "Condition ID": "new",
                        "Event Type": "resolved",
                        "Previous Status": "proposed",
                        "Current Status": "resolved",
                        "Dispute Count": "0",
                        "Resolved At": "2026-07-28T12:00:00Z",
                        "Resolved Outcome": "No",
                        "Yes Resolution Probability": "0.0",
                        "Automatically Resolved": "true",
                        "Resolution Details": (
                            "outcome=No; yes_probability=0.0; "
                            "resolved_at=2026-07-28T12:00:00Z; "
                            "automatically_resolved=true"
                        ),
                    }
                ],
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual((appended, total), (1, 2))
        self.assertIn("Resolved Outcome", content)
        self.assertIn("Resolution Details", content)
        self.assertIn("outcome=No", content)

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
