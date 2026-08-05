import json
import tempfile
import unittest
from pathlib import Path

from signal_research.forecasting import (
    append_forecast,
    build_forecast_record,
    validate_forecast_record,
)


class ForecastingTests(unittest.TestCase):
    def _record(self):
        return build_forecast_record(
            as_of_et="2026-08-05T13:31:00-04:00",
            created_at_utc="2026-08-05T17:31:00+00:00",
            forecaster="user",
            event_id="strait_of_hormuz_traffic_normal_aug_31_2026",
            question="Will traffic through the Strait of Hormuz return to normal by August 31, 2026?",
            resolution_deadline="2026-08-31",
            market_probability_source="user_stated_in_chat",
            market_probability=15.5,
            independent_probability=12.5,
            plausible_low=5.0,
            plausible_high=25.0,
            confidence_level="moderate_low",
            rationale="Midpoint of an initial 10%-15% independent estimate band.",
            catalysts_raise_probability=["Sustained commercial transit recovery"],
            catalysts_lower_probability=["Renewed attacks or mining incidents"],
            evidence_needed=["Exact market resolution rules"],
        )

    def test_edge_and_range_are_derived(self):
        record = self._record()
        self.assertEqual(record["edge_pp"], -3.0)
        self.assertEqual(record["range_width_pp"], 20.0)
        self.assertTrue(record["forecast_id"].startswith("forecast-"))

    def test_point_estimate_must_be_inside_range(self):
        with self.assertRaises(ValueError):
            build_forecast_record(
                as_of_et="2026-08-05T13:31:00-04:00",
                forecaster="user",
                event_id="x",
                question="Question",
                resolution_deadline="2026-08-31",
                market_probability=15.5,
                independent_probability=30.0,
                plausible_low=5.0,
                plausible_high=25.0,
                confidence_level="moderate_low",
            )

    def test_unknown_confidence_is_rejected(self):
        with self.assertRaises(ValueError):
            build_forecast_record(
                as_of_et="2026-08-05T13:31:00-04:00",
                forecaster="user",
                event_id="x",
                question="Question",
                resolution_deadline="2026-08-31",
                market_probability=15.5,
                independent_probability=12.5,
                plausible_low=5.0,
                plausible_high=25.0,
                confidence_level="pretty_sure",
            )

    def test_append_is_duplicate_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast_history.jsonl"
            record = self._record()
            self.assertTrue(append_forecast(path, record))
            self.assertFalse(append_forecast(path, record))
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_initial_history_record_is_valid(self):
        path = Path("signal_records/forecast_history.jsonl")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        validate_forecast_record(record)
        self.assertEqual(record["market_probability"], 15.5)
        self.assertEqual(record["independent_probability"], 12.5)
        self.assertEqual(record["plausible_low"], 5.0)
        self.assertEqual(record["plausible_high"], 25.0)
        self.assertEqual(record["confidence_level"], "moderate_low")


if __name__ == "__main__":
    unittest.main()
