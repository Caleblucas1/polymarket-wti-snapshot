from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecast_records.forecasting import (  # noqa: E402
    build_report,
    discover_records,
    effective_forecast,
    render_markdown,
    score_record,
    validate_record,
)


def binary_record(*, project: str = "signals", status: str = "resolved") -> dict:
    market_probability = 0.55 if project == "polymarket" else None
    initial_probability = 0.70
    return {
        "schema_version": 1,
        "forecast_id": f"{project.upper()}-TEST-20260101-001",
        "project": project,
        "status": status,
        "question": "Will the defined event occur by 2026-01-31 23:59 UTC?",
        "target": {
            "event_or_asset": "Test event",
            "forecast_type": "binary_probability",
            "horizon_start_utc": "2026-01-01T00:00:00Z",
            "horizon_end_utc": "2026-01-31T23:59:00Z",
            "information_cutoff_utc": "2025-12-31T20:00:00Z",
        },
        "resolution": {
            "source": "Official source",
            "rule": "Resolve YES only if the official source confirms the event by the deadline.",
            "resolved_at_utc": "2026-02-01T00:15:00Z" if status == "resolved" else None,
            "outcome": 1 if status == "resolved" else None,
        },
        "initial_forecast": {
            "created_at_utc": "2025-12-31T20:05:00Z",
            "probability": initial_probability,
            "numeric_value": None,
            "distribution": None,
            "benchmark_name": "reference_class_base_rate",
            "benchmark_value": 0.50,
        },
        "outside_view": {
            "reference_class": "Comparable historical events",
            "base_rate": 0.50,
            "source_notes": "Ten comparable events, five resolved YES.",
        },
        "decomposition": [
            {
                "driver": "Official preparations",
                "estimated_state": "Advanced",
                "effect_on_forecast": "up",
                "weight_or_probability": 0.6,
            }
        ],
        "evidence": {
            "supporting": ["Public preparations are visible."],
            "disconfirming": ["The deadline could slip."],
            "alternative_scenarios": ["A partial event does not satisfy the rule."],
        },
        "applicability": {
            "market_regime": ["event-driven"],
            "asset_classes": ["prediction-markets"],
            "invalidating_conditions": ["Official cancellation."],
        },
        "updates": [
            {
                "timestamp_utc": "2026-01-15T12:00:00Z",
                "old_probability": 0.70,
                "new_probability": 0.80,
                "old_numeric_value": None,
                "new_numeric_value": None,
                "new_evidence": "The official timetable was published.",
                "evidence_was_expected": False,
                "regime_changed": False,
                "market_moved_first": False,
            }
        ],
        "polymarket_comparison": {
            "market_slug": "test-event" if project == "polymarket" else None,
            "market_probability_at_cutoff": market_probability,
            "project_minus_market_probability": (
                initial_probability - market_probability if market_probability is not None else None
            ),
        },
        "scoring": {
            "primary_metric": "brier",
            "project_score": None,
            "benchmark_score": None,
            "relative_improvement": None,
            "out_of_sample": True,
        },
        "postmortem": {
            "completed": status == "resolved",
            "error_categories": [],
            "what_worked": "The timetable update was informative." if status == "resolved" else "",
            "what_failed": "" if status == "resolved" else "",
            "process_changes": [],
        },
        "audit": {
            "immutable_original_preserved": True,
            "real_money_trading_authorized": False,
        },
    }


def numeric_record() -> dict:
    record = binary_record()
    record["forecast_id"] = "SIGNALS-NUMERIC-20260101-001"
    record["target"]["forecast_type"] = "numeric"
    record["initial_forecast"].update(
        {
            "probability": None,
            "numeric_value": 12.0,
            "benchmark_value": 10.0,
            "benchmark_name": "no_change",
        }
    )
    record["outside_view"]["base_rate"] = 10.0
    record["resolution"]["outcome"] = 14.0
    record["updates"] = [
        {
            "timestamp_utc": "2026-01-15T12:00:00Z",
            "old_probability": None,
            "new_probability": None,
            "old_numeric_value": 12.0,
            "new_numeric_value": 13.0,
            "new_evidence": "A new data release raised the estimate.",
            "evidence_was_expected": False,
            "regime_changed": False,
            "market_moved_first": None,
        }
    ]
    record["scoring"]["primary_metric"] = "absolute_error"
    record["polymarket_comparison"] = {
        "market_slug": None,
        "market_probability_at_cutoff": None,
        "project_minus_market_probability": None,
    }
    return record


class ForecastValidationTests(unittest.TestCase):
    def test_valid_resolved_binary_record(self) -> None:
        issues = validate_record(binary_record())
        self.assertEqual([issue for issue in issues if issue.severity == "error"], [])

    def test_draft_may_be_incomplete_but_auditable(self) -> None:
        record = binary_record(status="open")
        record["status"] = "draft"
        record["question"] = ""
        record["decomposition"] = []
        record["evidence"] = {"supporting": [], "disconfirming": [], "alternative_scenarios": []}
        record["applicability"] = {"market_regime": [], "asset_classes": [], "invalidating_conditions": []}
        issues = validate_record(record)
        self.assertEqual([issue for issue in issues if issue.severity == "error"], [])

    def test_open_record_rejects_missing_base_rate_and_contrary_evidence(self) -> None:
        record = binary_record(status="open")
        record["outside_view"]["base_rate"] = None
        record["evidence"]["disconfirming"] = []
        errors = [issue.path for issue in validate_record(record) if issue.severity == "error"]
        self.assertIn("outside_view.base_rate", errors)
        self.assertIn("evidence.disconfirming", errors)

    def test_update_chain_must_match_prior_probability(self) -> None:
        record = binary_record()
        record["updates"][0]["old_probability"] = 0.65
        errors = [issue.path for issue in validate_record(record) if issue.severity == "error"]
        self.assertIn("updates[0].old_probability", errors)

    def test_polymarket_divergence_is_verified(self) -> None:
        record = binary_record(project="polymarket")
        record["polymarket_comparison"]["project_minus_market_probability"] = 0.99
        errors = [issue.path for issue in validate_record(record) if issue.severity == "error"]
        self.assertIn("polymarket_comparison.project_minus_market_probability", errors)

    def test_real_money_authorization_is_rejected(self) -> None:
        record = binary_record()
        record["audit"]["real_money_trading_authorized"] = True
        errors = [issue.path for issue in validate_record(record) if issue.severity == "error"]
        self.assertIn("audit.real_money_trading_authorized", errors)


class ForecastScoringTests(unittest.TestCase):
    def test_binary_score_uses_latest_pre_resolution_update(self) -> None:
        record = binary_record()
        self.assertEqual(effective_forecast(record), 0.80)
        score = score_record(record)
        self.assertAlmostEqual(score["project_score"], 0.04)
        self.assertAlmostEqual(score["benchmark_score"], 0.25)
        self.assertAlmostEqual(score["relative_improvement"], 0.84)

    def test_numeric_absolute_error(self) -> None:
        score = score_record(numeric_record())
        self.assertEqual(score["effective_forecast"], 13.0)
        self.assertEqual(score["project_score"], 1.0)
        self.assertEqual(score["benchmark_score"], 4.0)
        self.assertEqual(score["relative_improvement"], 0.75)

    def test_project_vs_market_report_and_calibration(self) -> None:
        report = build_report([binary_record(project="polymarket"), binary_record(project="signals")])
        comparison = report["scoring"]["project_vs_polymarket"]
        self.assertEqual(comparison["n"], 1)
        self.assertAlmostEqual(comparison["project_brier"], 0.04)
        self.assertAlmostEqual(comparison["market_brier"], 0.2025)
        self.assertEqual(report["calibration"]["project_probability_buckets"][0]["n"], 2)
        markdown = render_markdown(report)
        self.assertIn("Forecast accuracy and calibration report", markdown)
        self.assertIn("Project versus Polymarket", markdown)

    def test_invalid_records_are_not_scored(self) -> None:
        invalid = binary_record()
        invalid["audit"]["immutable_original_preserved"] = False
        report = build_report([invalid])
        self.assertEqual(report["invalid_record_count"], 1)
        self.assertEqual(report["scoring"]["resolved_scored_count"], 0)

    def test_discovery_only_loads_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text(json.dumps(binary_record()))
            (root / "README.md").write_text("ignored")
            self.assertEqual([path.name for path in discover_records(root)], ["a.json"])


if __name__ == "__main__":
    unittest.main()
