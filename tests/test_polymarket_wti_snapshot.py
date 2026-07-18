import argparse
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from polymarket_wti_snapshot import (
    all_markets_closed,
    collect_rows_and_ranges,
    fetch_histories,
    merge_and_write_range_csv,
    missing_snapshot_targets,
    probability_range,
    prices_at_or_before,
    merge_and_write_csv,
    run_snapshot,
    snapshot_targets,
    yes_token_id,
)


class SnapshotTests(unittest.TestCase):
    def test_detects_only_fully_closed_events(self):
        self.assertTrue(all_markets_closed([{"closed": True}, {"closed": "true"}]))
        self.assertFalse(all_markets_closed([{"closed": True}, {"closed": False}]))
        self.assertFalse(all_markets_closed([]))

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

    def test_calculates_trailing_twenty_four_hour_range(self):
        target = datetime.fromtimestamp(200000, tz=ZoneInfo("UTC"))
        history = [
            {"t": target.timestamp() - 90000, "p": 0.01},
            {"t": target.timestamp() - 86400, "p": 0.15},
            {"t": target.timestamp() - 3600, "p": 0.45},
            {"t": target.timestamp() + 60, "p": 0.99},
        ]
        self.assertEqual(probability_range(history, target), (0.15, 0.45))

    def test_uses_zero_width_range_for_carried_forward_snapshot(self):
        target = datetime.fromtimestamp(200000, tz=ZoneInfo("UTC"))
        markets = [{"groupItemTitle": "↑ $80", "clobTokenIds": '["yes-token"]'}]
        history = [{"t": target.timestamp() - 2 * 86400, "p": 1.0}]
        with patch(
            "polymarket_wti_snapshot.fetch_histories",
            return_value={"yes-token": history},
        ):
            _, range_rows = collect_rows_and_ranges(
                object(), markets, [target], timeout=5
            )

        self.assertEqual(range_rows[0]["Low"], 100.0)
        self.assertEqual(range_rows[0]["High"], 100.0)

    def test_finds_only_missing_snapshot_targets(self):
        targets = [
            datetime(2026, 7, 16, 9, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 7, 17, 9, tzinfo=ZoneInfo("America/New_York")),
        ]
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "snapshot.csv"
            path.write_text("Price Bin,2026-07-16\n↑ $90,22.0\n", encoding="utf-8")
            missing = missing_snapshot_targets(path, targets)
        self.assertEqual([target.date().isoformat() for target in missing], ["2026-07-17"])

    def test_fetches_histories_in_batches_of_twenty(self):
        class FakeResponse:
            def __init__(self, token_ids):
                self.token_ids = token_ids

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "history": {
                        token_id: [{"t": 100, "p": 0.5}]
                        for token_id in self.token_ids
                    }
                }

        class FakeSession:
            def __init__(self):
                self.payloads = []

            def post(self, _url, *, json, timeout):
                self.payloads.append((json, timeout))
                return FakeResponse(json["markets"])

        session = FakeSession()
        token_ids = [f"token-{index}" for index in range(21)]
        targets = [datetime.fromtimestamp(200, tz=ZoneInfo("UTC"))]
        histories = fetch_histories(session, token_ids, targets, timeout=5)

        self.assertEqual(len(session.payloads), 2)
        self.assertEqual(len(session.payloads[0][0]["markets"]), 20)
        self.assertEqual(len(session.payloads[1][0]["markets"]), 1)
        self.assertIsInstance(session.payloads[0][0]["start_ts"], int)
        self.assertIsInstance(session.payloads[0][0]["end_ts"], int)
        self.assertEqual(set(histories), set(token_ids))

    def test_regenerates_chart_without_api_calls_when_csv_is_current(self):
        target = datetime(2026, 7, 17, 9, tzinfo=ZoneInfo("America/New_York"))
        with tempfile.TemporaryDirectory() as temp_directory:
            output = Path(temp_directory) / "snapshot.csv"
            range_output = Path(temp_directory) / "snapshot_ranges.csv"
            output.write_text("Price Bin,2026-07-17\n↑ $90,25.0\n", encoding="utf-8")
            range_output.write_text(
                "Price Bin,Date,Low,High\n↑ $90,2026-07-17,20.0,30.0\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                output=output,
                range_output=range_output,
                chart_output=Path(temp_directory) / "chart.html",
                slug="example",
                title="Example",
                days=7,
                hour=9,
                timeout=5,
                no_chart=False,
            )
            with (
                patch("polymarket_wti_snapshot.snapshot_targets", return_value=[target]),
                patch("polymarket_wti_snapshot.write_snapshot_chart", return_value=1) as chart,
                patch("polymarket_wti_snapshot.build_session") as session,
            ):
                result = run_snapshot(args)

        self.assertEqual(result.status, "current")
        chart.assert_called_once_with(args)
        session.assert_not_called()

    def test_reports_fully_closed_event(self):
        target = datetime(2026, 7, 17, 9, tzinfo=ZoneInfo("America/New_York"))
        with tempfile.TemporaryDirectory() as temp_directory:
            args = argparse.Namespace(
                output=Path(temp_directory) / "missing.csv",
                chart_output=Path(temp_directory) / "chart.html",
                slug="closed-event",
                days=1,
                hour=9,
                timeout=5,
                no_chart=True,
            )
            with (
                patch("polymarket_wti_snapshot.snapshot_targets", return_value=[target]),
                patch("polymarket_wti_snapshot.build_session"),
                patch(
                    "polymarket_wti_snapshot.fetch_event",
                    return_value={"markets": [{"closed": True}]},
                ),
            ):
                result = run_snapshot(args)

        self.assertEqual(result.status, "closed")
        self.assertEqual(result.exit_code, 0)

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

    def test_appends_ranges_without_revising_existing_values(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "ranges.csv"
            path.write_text(
                "Price Bin,Date,Low,High\n↑ $90,2026-07-16,20.0,30.0\n",
                encoding="utf-8",
            )
            added, row_count = merge_and_write_range_csv(
                path,
                [
                    {"Price Bin": "↑ $90", "Date": "2026-07-16", "Low": 1.0, "High": 99.0},
                    {"Price Bin": "↑ $90", "Date": "2026-07-17", "Low": 22.0, "High": 40.0},
                ],
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual((added, row_count), (1, 2))
        self.assertIn("↑ $90,2026-07-16,20.0,30.0", content)
        self.assertIn("↑ $90,2026-07-17,22.0,40.0", content)
        self.assertNotIn("99.0", content)


if __name__ == "__main__":
    unittest.main()
