import unittest
from datetime import date

from signal_research.audit_s012_btc_qqq_rv import (
    benchmark_audit,
    matched_null_distribution,
    nonoverlapping_events,
)
from signal_research.backtest_s012_btc_qqq_rv import EventOutcome


def outcome(trigger, entry, exit_, net, split="development"):
    return EventOutcome(
        trigger_date=date.fromisoformat(trigger),
        entry_date=date.fromisoformat(entry),
        exit_date=date.fromisoformat(exit_),
        horizon="90",
        split=split,
        regime="test",
        gross_return=net + 0.002,
        net_return=net,
        max_adverse_excursion=-0.05,
        max_drawdown=-0.10,
        drawdown_10=False,
        drawdown_20=False,
        drawdown_30=False,
    )


class S012AuditTests(unittest.TestCase):
    def test_nonoverlapping_events_do_not_count_clustered_holds_as_independent(self):
        rows = [
            outcome("2020-01-01", "2020-01-01", "2020-04-01", 0.10),
            outcome("2020-01-05", "2020-01-05", "2020-04-05", 0.20),
            outcome("2020-04-02", "2020-04-02", "2020-07-01", 0.30),
        ]
        selected = nonoverlapping_events(rows)
        self.assertEqual(["2020-01-01", "2020-04-02"], [r.trigger_date.isoformat() for r in selected])

    def test_matched_null_draws_one_date_per_signal_event_without_row_duplication(self):
        signal = [
            outcome("2020-01-01", "2020-01-01", "2020-04-01", 0.30),
            outcome("2021-01-01", "2021-01-01", "2021-04-01", 0.40),
        ]
        unconditional = [
            outcome("2020-02-01", "2020-02-01", "2020-05-01", 0.10),
            outcome("2020-03-01", "2020-03-01", "2020-06-01", 0.20),
            outcome("2021-02-01", "2021-02-01", "2021-05-01", 0.05),
            outcome("2021-03-01", "2021-03-01", "2021-06-01", 0.15),
        ]
        values = matched_null_distribution(signal, unconditional, simulations=2000, seed=1)
        self.assertEqual(2000, len(values))
        self.assertAlmostEqual(0.125, sum(values) / len(values), places=2)

    def test_audit_reports_target_without_claiming_production(self):
        signal = [outcome("2020-01-01", "2020-01-01", "2020-04-01", 0.30)]
        unconditional = [
            outcome("2020-02-01", "2020-02-01", "2020-05-01", 0.10),
            outcome("2020-03-01", "2020-03-01", "2020-06-01", 0.15),
        ]
        result = benchmark_audit(signal, unconditional, simulations=2000, seed=2)
        self.assertTrue(result["matched_null"]["clears_25pct_improvement_target"])
        self.assertEqual(1, result["observed"]["event_count"])


if __name__ == "__main__":
    unittest.main()
