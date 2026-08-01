import unittest

from signal_research.backtest import TradeResult, summarize, summarize_by_regime
from signal_research.confidence import confidence_score
from signal_research.models import ConfidenceEvidence
from signal_research.rebound import ReboundConfig, evaluate_rebound
from signal_research.registry import get_candidate, load_candidates


class RegistryTests(unittest.TestCase):
    def test_registry_has_unique_candidates_and_s009_controls(self):
        candidates = load_candidates()
        self.assertEqual(len(candidates), len({item.signal_id for item in candidates}))
        s009 = get_candidate("S-009")
        self.assertEqual(s009.metadata["weighted_aggregate"], "deferred")
        self.assertEqual(s009.metadata["rebound_components"], 4)
        self.assertEqual(s009.metadata["maximum_volatility_lookback"], 30)

    def test_unextracted_sources_are_not_overstated(self):
        self.assertEqual(get_candidate("S-002").status, "needs_source_extraction")
        self.assertEqual(get_candidate("S-004").status, "needs_source_extraction")


class ConfidenceTests(unittest.TestCase):
    def test_out_of_sample_evidence_increases_score(self):
        weak = ConfidenceEvidence(sample_size=20, data_quality=0.5, decay_risk=0.5)
        strong = ConfidenceEvidence(
            sample_size=200,
            out_of_sample_trades=100,
            out_of_sample_sharpe=1.25,
            regime_coverage=0.8,
            implementation_cost_bps=2,
            gross_edge_bps=12,
            decay_risk=0.2,
            data_quality=0.9,
        )
        self.assertGreater(confidence_score(strong), confidence_score(weak))

    def test_costs_can_remove_edge_credit(self):
        profitable = ConfidenceEvidence(gross_edge_bps=10, implementation_cost_bps=2, decay_risk=0)
        consumed = ConfidenceEvidence(gross_edge_bps=10, implementation_cost_bps=12, decay_risk=0)
        self.assertGreater(confidence_score(profitable), confidence_score(consumed))


class ReboundTests(unittest.TestCase):
    def test_lookback_cannot_exceed_one_month(self):
        with self.assertRaises(ValueError):
            ReboundConfig(volatility_lookback=31)

    def test_evaluates_all_four_components(self):
        prices = [100 + (i % 3) * 0.1 for i in range(22)] + [98.0, 98.2, 98.6, 99.2, 99.8, 100.4, 101.0]
        result = evaluate_rebound(
            prices,
            reference_level=100.0,
            config=ReboundConfig(volatility_lookback=21, sustain_bars=5),
        )
        self.assertTrue(result.local_low_reversal)
        self.assertTrue(result.reference_level_reclaim)
        self.assertTrue(result.trend_confirmation)
        self.assertTrue(result.sustained_recovery)
        self.assertEqual(result.score, 4)
        self.assertEqual(result.stage, "full")

    def test_requires_only_past_and_current_prices(self):
        with self.assertRaises(ValueError):
            evaluate_rebound([100.0, 101.0], reference_level=100.0)


class BacktestTests(unittest.TestCase):
    def test_cost_aware_metrics_and_regimes(self):
        rows = [
            TradeResult("S-009", "t1", 0.02, 0.001, 0.005, "macro", True, False),
            TradeResult("S-009", "t2", -0.01, 0.001, -0.002, "macro", False, True),
            TradeResult("S-009", "t3", 0.03, 0.002, 0.010, "crypto-specific", True, True),
        ]
        overall = summarize(rows)
        self.assertEqual(overall.observations, 3)
        self.assertAlmostEqual(overall.hit_rate, 2 / 3)
        grouped = summarize_by_regime(rows)
        self.assertEqual(set(grouped), {"macro", "crypto-specific"})
        self.assertLess(overall.total_net_return, 0.05)


if __name__ == "__main__":
    unittest.main()
