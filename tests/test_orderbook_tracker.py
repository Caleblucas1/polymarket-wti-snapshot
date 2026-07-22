import tempfile
import unittest
from pathlib import Path

from polymarket_orderbook import (
    instance_from_market,
    logical_ids,
    reconcile_instances,
    summarize_book,
    write_report,
)


class OrderbookTrackerTests(unittest.TestCase):
    def market(self, label, condition_id, *, closed=False, accepting=True):
        return {
            "id": condition_id.removeprefix("condition-"),
            "groupItemTitle": label,
            "question": f"Question for {label}",
            "conditionId": condition_id,
            "clobTokenIds": '["yes-token", "no-token"]',
            "outcomes": '["Yes", "No"]',
            "createdAt": "2026-07-20T12:00:00Z",
            "active": True,
            "closed": closed,
            "acceptingOrders": accepting,
            "enableOrderBook": True,
            "volumeNum": 100,
            "liquidityNum": 20,
        }

    def test_direction_is_part_of_logical_identity_but_not_threshold_family(self):
        up = logical_ids("wti-july", "↑ $80")
        down = logical_ids("wti-july", "↓ $80")
        self.assertNotEqual(up[0], down[0])
        self.assertEqual(up[1], down[1])
        self.assertEqual(up[1], "wti-july::threshold-80")
        self.assertEqual((up[2], down[2]), ("up", "down"))

    def test_new_same_contract_condition_is_a_replacement(self):
        first = instance_from_market(
            "wti-july", "wti", self.market("↑ $90", "condition-old"), "t1"
        )
        existing, _ = reconcile_instances([], [first], "t1")
        second = instance_from_market(
            "wti-july", "wti", self.market("↑ $90", "condition-new"), "t2"
        )
        updated, events = reconcile_instances(existing, [second], "t2")
        new_row = next(row for row in updated if row["Condition ID"] == "condition-new")
        self.assertEqual(new_row["Instance Number"], "2")
        self.assertEqual(new_row["Replaces Condition ID"], "condition-old")
        self.assertIn("replaced", [event["Event Type"] for event in events])
        self.assertIn("disappeared", [event["Event Type"] for event in events])

    def test_opposite_direction_is_related_not_replaced(self):
        up = instance_from_market(
            "wti-july", "wti", self.market("↑ $80", "condition-up"), "t1"
        )
        existing, _ = reconcile_instances([], [up], "t1")
        down = instance_from_market(
            "wti-july", "wti", self.market("↓ $80", "condition-down"), "t2"
        )
        updated, events = reconcile_instances(existing, [up, down], "t2")
        down_row = next(row for row in updated if row["Condition ID"] == "condition-down")
        self.assertEqual(down_row["Replaces Condition ID"], "")
        self.assertIn("related-threshold-appeared", [event["Event Type"] for event in events])

    def test_depth_uses_best_quotes_even_when_book_is_unsorted(self):
        summary = summarize_book({
            "timestamp": "1", "hash": "abc",
            "bids": [
                {"price": "0.40", "size": "10"},
                {"price": "0.45", "size": "20"},
                {"price": "0.43", "size": "30"},
            ],
            "asks": [
                {"price": "0.60", "size": "40"},
                {"price": "0.50", "size": "50"},
                {"price": "0.54", "size": "60"},
            ],
        })
        self.assertEqual(summary["Best Bid"], "0.45")
        self.assertEqual(summary["Best Ask"], "0.5")
        self.assertEqual(summary["Spread"], "0.05")
        self.assertEqual(summary["Bid Shares 5c"], "60")
        self.assertEqual(summary["Ask Shares 5c"], "110")

    def test_writes_depth_report_table(self):
        row = {
            "Event Key": "wti-july", "Market Label": "↑ $90",
            "Book Status": "available", "Best Bid": "0.4", "Best Ask": "0.5",
            "Spread": "0.1", "Bid Shares 5c": "10", "Ask Shares 5c": "20",
            "Instance Volume": "100", "Logical Lifetime Volume": "100",
            "Condition ID": "condition", "Logical Market ID": "wti-july::up-90",
        }
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "report.html"
            write_report(path, [row], [])
            content = path.read_text(encoding="utf-8")
        self.assertIn("Latest depth for every present market", content)
        self.assertIn("↑ $90", content)


if __name__ == "__main__":
    unittest.main()
