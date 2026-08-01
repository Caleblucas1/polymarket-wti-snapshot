import json
import unittest
from pathlib import Path

from signal_research.backtest import TradeResult, summarize, summarize_by_regime
from signal_research.confidence import confidence_score
from signal_research.governance import (
    capital_rights,
    component_confidence_score,
    confidence_band,
    production_gate,
)
from signal_research.models import ConfidenceEvidence
from signal_research.rebound import ReboundConfig, evaluate_rebound
from signal_research.registry import get_candidate, load_candidates, validate_registry


ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_registry_is_valid_and_ids_are_unique(self):
        self.assertEqual(validate_registry(), [])
        candidates = load_candidates()
        self.assertEqual(len(candidates), len({item.signal_id for item in candidates}))
        self.assertEqual(len(candidates), len({item.registry_id for item in candidates}))

    def test_thematic_ids_resolve_legacy_collision(self):
        legacy_s009 = get_candidate("S-009")
        month_end = get_candidate("FLOW-MON-BTC-001")
        self.assertEqual(legacy_s009.registry_id, "CROSS-ASSET-REBOUND-001")
        self.assertEqual(month_end.signal_id, "S-010")
        self.assertEqual(get_candidate("SALSA-MONTH-END"), month_end)

    def test_month_end_chart_is_transcribed(self):
        item = get_candidate("FLOW-MON-BTC-001")
        returns = item.metadata["median_return_windows"]
        self.assertEqual(item.metadata["source_sample_months"], 30)
        self.assertAlmostEqual(returns["before"]["7"], -0.0147)
        self.assertAlmostEqual(returns["after"]["7"], 0.0207)
        self.assertEqual(item.confidence_score, 41)

    def test_confidence_components_recompute_exactly(self):
        for item in load_candidates():
            self.assertEqual(
                component_confidence_score(item.confidence_components),
                item.confidence_score,
            )
        self.assertEqual(confidence_band(41), "promising")

    def test_no_current_signal_has_live_capital_rights(self):
        for item in load_candidates():
            self.assertNotEqual(capital_rights(item), "capped_live")
            self.assertFalse(production_gate(item).valid_current_production)

    def test_degraded_signal_is_blocked_even_with_historical_interest(self):
        sndk = get_candidate("MICRO-ASIA-SNDK-001")
        self.assertEqual(sndk.operational_status.value, "degraded")
        self.assertEqual(capital_rights(sndk), "none")

    def test_ledgers_reference_registered_ids(self):
        ids = {item.registry_id for item in load_candidates()}
        evidence_path = ROOT / "signal_records" / "evidence_ledger.jsonl"
        evidence = [
            json.loads(line)
            for line in evidence_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(evidence)
        self.assertTrue(all(row["registry_id"] in ids for row in evidence))

        confidence_path = ROOT / "signal_records" / "confidence_history.jsonl"
        confidence = [
            json.loads(line)
            for line in confidence_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual({row["registry_id"] for row in confidence}, ids)

        statuses = json.loads(
            (ROOT / "signal_records" / "live_status.json").read_text(encoding="utf-8")
        )
        self.assertEqual({row["registry_id"] for row in statuses["records"]}, ids)


class ConfidenceTests(unittest.TestCase):
    def test_out_of_sample_evidence_increases_empirical_score(self):
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
