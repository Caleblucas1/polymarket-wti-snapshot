"""Deterministic candidate-stage evaluation for S-013.

This program distinguishes a qualitative source read from an executable trigger.
It never infers a numeric regional probability from chart pixels and never
creates a TTF position when required data is absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SIGNAL_ID = "S-013"
REGISTRY_ID = "ECMWF-WARM-WINTER-TTF-001"
CONFIDENCE_COMPONENTS = {
    "statistical_evidence": 0,
    "out_of_sample_evidence": 0,
    "economic_mechanism": 11,
    "regime_clarity": 6,
    "execution_quality": 3,
    "robustness": 2,
    "current_relevance": 10,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(source: dict[str, Any], *, source_sha256: str | None = None) -> dict[str, Any]:
    if source.get("signal_id") != SIGNAL_ID or source.get("registry_id") != REGISTRY_ID:
        raise ValueError("source identity does not match S-013")
    image = source.get("forecast_image")
    readiness = source.get("data_readiness")
    screenshot = source.get("screenshot")
    if not isinstance(image, dict) or not image.get("sha256"):
        raise ValueError("forecast image provenance is required")
    if not isinstance(readiness, dict):
        raise ValueError("data_readiness is required")
    if not isinstance(screenshot, dict) or not screenshot.get("exclusion_reason"):
        raise ValueError("separate embedded claims must be explicitly handled")

    trigger_evaluable = bool(
        readiness.get("machine_readable_august_2026_fixed_region_probability_available")
    )
    historical_weather = bool(readiness.get("historical_point_in_time_ecmwf_events_available"))
    historical_ttf = bool(readiness.get("historical_ice_ttf_settlements_available"))
    backtest_executable = trigger_evaluable and historical_weather and historical_ttf
    confidence_score = sum(CONFIDENCE_COMPONENTS.values())

    if backtest_executable:
        classification = "ready_for_frozen_backtest"
        stage = "backtest"
        operational_status = "backtest_in_progress"
    else:
        classification = "candidate_accepted_hypothesis_blocked_market_data_unavailable"
        stage = "hypothesis"
        operational_status = "ready_for_data"

    return {
        "signal_id": SIGNAL_ID,
        "registry_id": REGISTRY_ID,
        "evaluation_version": 1,
        "as_of": source["captured_at"],
        "classification": classification,
        "candidate_accepted": True,
        "stage": stage,
        "operational_status": operational_status,
        "qualified_source_read": {
            "weather_direction": "warm_europe",
            "ttf_weather_impulse": "bearish",
            "statement_strength": "qualitative_only",
            "canonical_probability_observed": None,
            "reason": "The supplied ECMWF map visually favors upper-tercile temperatures across much of Europe, but the fixed-region numeric probability is unavailable."
        },
        "canonical_rule": {
            "forecast": "August ECMWF SEAS5 DJF 2m temperature",
            "region": "35N-60N, 10W-30E",
            "trigger": "area-weighted upper-tercile probability >= 60%",
            "instrument": "equal-weight ICE Dutch TTF December-January-February monthly futures strip",
            "direction": "short",
            "entry": "next official ICE settlement after verified public release",
            "primary_exit": "official settlement after five ICE trading sessions",
            "round_trip_cost_eur_per_mwh": 0.05
        },
        "data_readiness": {
            "canonical_trigger_evaluable": trigger_evaluable,
            "historical_weather_events_available": historical_weather,
            "historical_ttf_settlements_available": historical_ttf,
            "backtest_executable": backtest_executable
        },
        "blocking_fields": [
            key
            for key, available in (
                ("machine_readable_ecmwf_fixed_region_probability", trigger_evaluable),
                ("point_in_time_historical_ecmwf_events", historical_weather),
                ("point_in_time_ice_ttf_settlements", historical_ttf),
            )
            if not available
        ],
        "excluded_evidence": [{
            "claim": screenshot.get("excluded_embedded_claim"),
            "reason": screenshot.get("exclusion_reason")
        }],
        "confidence_score": confidence_score,
        "confidence_band": "preliminary",
        "confidence_components": CONFIDENCE_COMPONENTS,
        "backtest_results": None,
        "shadow_position": None,
        "decision": "Preserve and prioritize the candidate for data acquisition; do not infer a trade from the screenshot and do not claim historical alpha.",
        "capital_rights": "none",
        "real_money_trading_authorized": False,
        "source_payload_sha256": source_sha256
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate S-013 ECMWF warm-winter TTF candidate")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    result = evaluate(source, source_sha256=_sha256(args.source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": result["classification"],
        "backtest_executable": result["data_readiness"]["backtest_executable"],
        "confidence_score": result["confidence_score"],
        "output": str(args.output)
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
