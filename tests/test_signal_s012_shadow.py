import unittest
from datetime import date, datetime, time, timedelta, timezone

from signal_research import backtest_s012_btc_qqq_rv as core
from signal_research import monitor_s012_btc_qqq_rv as monitor

UTC = timezone.utc


class MonitorTests(unittest.TestCase):
    def test_shadow_record_never_authorizes_money(self):
        btc = [
            core.PricePoint(
                date(2026, 6, 1) + timedelta(days=index),
                100 + index * 0.2 + (index % 3),
                datetime.combine(
                    date(2026, 6, 2) + timedelta(days=index),
                    time.min,
                    tzinfo=UTC,
                ),
            )
            for index in range(180)
        ]
        qqq = [
            core.PricePoint(
                day,
                200 + index * 0.1 + (index % 11),
                datetime.combine(day, time(21), tzinfo=UTC),
            )
            for index in range(180)
            if (day := date(2026, 6, 1) + timedelta(days=index)).weekday() < 5
        ]
        record = monitor.build_shadow_record(
            btc, qqq, as_of=date(2026, 11, 27), cost_bps=20
        )
        self.assertFalse(record["real_money_trading_authorized"])
        self.assertEqual("none", record["capital_rights"])
        self.assertEqual("untouched_prospective_shadow", record["record_type"])


if __name__ == "__main__":
    unittest.main()
