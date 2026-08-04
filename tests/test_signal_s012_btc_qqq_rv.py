import math
import unittest
from datetime import date, datetime, time, timedelta, timezone

from signal_research import backtest_s012_btc_qqq_rv as s012

UTC = timezone.utc


def point(day: date, close: float, available_hour: int = 0):
    available_date = day + timedelta(days=1) if available_hour == 0 else day
    return s012.PricePoint(
        day,
        close,
        datetime.combine(available_date, time(available_hour), tzinfo=UTC),
    )


class S012Tests(unittest.TestCase):
    def test_btc_daily_close_is_not_available_until_next_utc_midnight(self):
        payload = {
            "chart": {
                "error": None,
                "result": [
                    {
                        "timestamp": [
                            int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
                        ],
                        "indicators": {"quote": [{"close": [100.0]}]},
                    }
                ],
            }
        }
        rows = s012.parse_btc_prices(payload)
        self.assertEqual(date(2026, 1, 1), rows[0].session_date)
        self.assertEqual(datetime(2026, 1, 2, tzinfo=UTC), rows[0].available_at)

    def test_trigger_requires_rearm_and_fresh_crossover(self):
        base = datetime(2026, 1, 1, 21, tzinfo=UTC)
        ratios = [1.2, 0.9, 0.8, 1.1, 0.95, 0.7]
        observations = []
        for index, ratio in enumerate(ratios):
            day = date(2026, 1, 1) + timedelta(days=index)
            observations.append(
                s012.ComparableObservation(
                    decision_date=day,
                    decision_at=base + timedelta(days=index),
                    btc_close_date=day - timedelta(days=1),
                    btc_close=100,
                    qqq_close=100,
                    btc_rv=ratio,
                    qqq_rv=1.0,
                    ratio=ratio,
                    regime="test",
                )
            )
        self.assertEqual([1, 4], s012.extract_trigger_indices(observations))

    def test_realized_vol_uses_calendar_window(self):
        returns = [
            (
                date(2026, 1, 1) + timedelta(days=index),
                0.01 * ((-1) ** index),
            )
            for index in range(40)
        ]
        rv = s012.realized_volatility(
            returns,
            date(2026, 2, 9),
            lookback_days=30,
            annualization_days=365,
            minimum_observations=20,
        )
        expected = [
            value
            for row_date, value in returns
            if date(2026, 1, 10) < row_date <= date(2026, 2, 9)
        ]
        self.assertAlmostEqual(
            rv, s012.statistics.stdev(expected) * math.sqrt(365)
        )

    def test_event_entry_is_first_btc_close_after_qqq_decision(self):
        observation = s012.ComparableObservation(
            decision_date=date(2026, 1, 5),
            decision_at=datetime(2026, 1, 5, 21, tzinfo=UTC),
            btc_close_date=date(2026, 1, 4),
            btc_close=100,
            qqq_close=100,
            btc_rv=0.8,
            qqq_rv=1.0,
            ratio=0.8,
            regime="test",
        )
        points = [
            point(date(2026, 1, 4) + timedelta(days=index), 100 + index)
            for index in range(40)
        ]
        outcome = s012.event_outcome(
            0, [observation], points, 30, cost_bps=20
        )
        self.assertEqual(date(2026, 1, 5), outcome.entry_date)
        self.assertEqual(date(2026, 2, 4), outcome.exit_date)
        self.assertAlmostEqual((131 / 101 - 1) - 0.002, outcome.net_return)

    def test_max_drawdown_is_path_based(self):
        self.assertAlmostEqual(-0.25, s012.max_drawdown([100, 120, 90, 110]))

    def test_split_boundary_is_prospective_only_after_frozen_date(self):
        self.assertEqual("development", s012.split_name(date(2021, 12, 31)))
        self.assertEqual(
            "historical_validation_source_exposed",
            s012.split_name(date(2026, 8, 3)),
        )
        self.assertEqual(
            "prospective_untouched", s012.split_name(date(2026, 8, 4))
        )

    def test_improvement_target_is_explicit(self):
        result = s012.improvement(
            {"mean_net_return": 0.10}, {"mean_net_return": 0.08}
        )
        self.assertAlmostEqual(
            0.25, result["relative_improvement_vs_abs_benchmark_mean"]
        )
        self.assertTrue(result["clears_25pct_conditional_improvement_target"])

    def test_source_chart_is_not_claimed_as_exactly_reproduced(self):
        btc = [
            point(
                date(2020, 1, 1) + timedelta(days=index),
                100 + index * 0.1 + (index % 7),
            )
            for index in range(900)
        ]
        qqq = [
            s012.PricePoint(
                day,
                200 + index * 0.05 + (index % 5),
                datetime.combine(day, time(21), tzinfo=UTC),
            )
            for index in range(900)
            if (day := date(2020, 1, 1) + timedelta(days=index)).weekday() < 5
        ]
        result = s012.run_backtest(btc, qqq)
        self.assertEqual(
            "not_exactly_verifiable_from_image_only",
            result["source_chart_reproduction"]["status"],
        )
        self.assertFalse(result["decision"]["real_money_trading_authorized"])
        self.assertFalse(result["decision"]["production_stage_permitted"])


if __name__ == "__main__":
    unittest.main()
