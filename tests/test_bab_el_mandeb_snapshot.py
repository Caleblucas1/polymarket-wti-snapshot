import unittest

from bab_el_mandeb_snapshot import deadline_sort_key, selected_markets


class BabElMandebSnapshotTests(unittest.TestCase):
    def test_excludes_closed_deadlines_by_default(self):
        markets = [
            {"groupItemTitle": "June 30", "closed": True},
            {"groupItemTitle": "July 31", "closed": False},
            {"groupItemTitle": "August 31"},
        ]
        self.assertEqual(
            [market["groupItemTitle"] for market in selected_markets(markets)],
            ["July 31", "August 31"],
        )
        self.assertEqual(len(selected_markets(markets, include_closed=True)), 3)

    def test_orders_deadlines_by_calendar_date(self):
        labels = ["December 31", "July 31", "September 30", "August 31"]
        self.assertEqual(
            sorted(labels, key=deadline_sort_key),
            ["July 31", "August 31", "September 30", "December 31"],
        )


if __name__ == "__main__":
    unittest.main()
