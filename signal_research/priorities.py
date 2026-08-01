from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_PRIORITIES_PATH = Path("signal_research/research_priorities.json")
DEFAULT_HYPOTHESES_PATH = Path("signal_hypotheses.json")
DEFAULT_LIVE_CONFIG_DIR = Path("signal_research/live_tests")

CROSS_ASSET_ID = "CROSS-ASSET-REBOUND-001"
FLOW_MONTH_ID = "FLOW-MON-BTC-001"
APPROVED_FLOW_TEST_ID = "FLOW-MON-BTC-2026-08"
EXPECTED_CROSS_ASSET_BLOCKERS = [
    "mechanical common-shock detector",
    "pre-shock reference-level rule",
    "maximum event horizon",
    "exact unweighted basket timestamp aggregation rule",
]


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_priorities(path: str | Path = DEFAULT_PRIORITIES_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_hypotheses(path: str | Path = DEFAULT_HYPOTHESES_PATH) -> dict[str, Any]:
    return _read_json(path)


def _canonical_hypothesis(payload: dict[str, Any], registry_id: str) -> dict[str, Any] | None:
    for row in payload.get("hypotheses", []):
        if (
            isinstance(row, dict)
            and row.get("registry_id") == registry_id
            and row.get("variant") == "canonical"
        ):
            return row
    return None


def discover_flow_month_configs(live_config_dir: str | Path = DEFAULT_LIVE_CONFIG_DIR) -> list[str]:
    root = Path(live_config_dir)
    if not root.exists():
        return []
    return sorted(path.stem for path in root.glob("FLOW-MON-BTC-*.json"))


def validate_priorities(
    priorities_path: str | Path = DEFAULT_PRIORITIES_PATH,
    hypotheses_path: str | Path = DEFAULT_HYPOTHESES_PATH,
    live_config_dir: str | Path = DEFAULT_LIVE_CONFIG_DIR,
) -> list[str]:
    errors: list[str] = []
    priorities = load_priorities(priorities_path)
    hypotheses = load_hypotheses(hypotheses_path)

    if priorities.get("decision_origin") != "explicit_user_reprioritization":
        errors.append("priority decision must preserve its explicit user origin")
    if priorities.get("real_money_trading_authorized") is not False:
        errors.append("priority decision must not authorize real-money trading")
    if priorities.get("priority_order", [])[:2] != [CROSS_ASSET_ID, FLOW_MONTH_ID]:
        errors.append("cross-asset rebound must rank ahead of the BTC monthly-flow signal")

    signals = priorities.get("signals")
    if not isinstance(signals, dict):
        return errors + ["signals must be an object"]

    cross = signals.get(CROSS_ASSET_ID)
    flow = signals.get(FLOW_MONTH_ID)
    if not isinstance(cross, dict):
        errors.append(f"missing {CROSS_ASSET_ID} priority record")
    if not isinstance(flow, dict):
        errors.append(f"missing {FLOW_MONTH_ID} priority record")
    if errors:
        return errors

    assert isinstance(cross, dict)
    assert isinstance(flow, dict)

    if cross.get("priority_rank") != 1:
        errors.append("cross-asset rebound must have priority rank 1")
    if cross.get("status") != "design_blocked_next_live_candidate":
        errors.append("cross-asset rebound must remain design-blocked before live launch")
    if cross.get("live_launch_authorized") is not False:
        errors.append("cross-asset rebound live launch must remain unauthorized while blocked")
    if cross.get("current_blockers") != EXPECTED_CROSS_ASSET_BLOCKERS:
        errors.append("cross-asset rebound blockers must match the frozen canonical hypothesis")
    if cross.get("canonical_aggregation") != "unweighted and mechanically frozen before any live event":
        errors.append("cross-asset canonical aggregation must remain unweighted")
    experimental = str(cross.get("experimental_aggregation", "")).lower()
    if "volatility-weighted" not in experimental or "separately" not in experimental:
        errors.append("volatility-weighted aggregation must remain a separate experiment")

    canonical_cross = _canonical_hypothesis(hypotheses, CROSS_ASSET_ID)
    if canonical_cross is None:
        errors.append("missing frozen cross-asset canonical hypothesis")
    else:
        if canonical_cross.get("freeze_status") != "blocked":
            errors.append("priority change must not silently unfreeze cross-asset canonical rules")
        if canonical_cross.get("blocking_fields") != EXPECTED_CROSS_ASSET_BLOCKERS:
            errors.append("priority blockers diverge from signal_hypotheses.json")

    if flow.get("priority_tier") != "low_priority_infrastructure_only":
        errors.append("BTC monthly-flow signal must be infrastructure-only")
    if flow.get("status") != "complete_current_one_off_then_dormant":
        errors.append("BTC monthly-flow signal must become dormant after the current test")
    if flow.get("current_one_off_test_id") != APPROVED_FLOW_TEST_ID:
        errors.append("only the August 2026 monthly-flow test is approved")
    if flow.get("future_month_launches_enabled") is not False:
        errors.append("future monthly-flow launches must be disabled")
    if flow.get("automatic_successor_creation_enabled") is not False:
        errors.append("automatic monthly-flow successor creation must be disabled")
    if flow.get("post_current_test_status") != "dormant":
        errors.append("monthly-flow signal must become dormant after the current test")
    if flow.get("capital_rights_from_current_test") != "none":
        errors.append("the current monthly-flow observation must grant no capital rights")

    discovered = discover_flow_month_configs(live_config_dir)
    unapproved = [test_id for test_id in discovered if test_id != APPROVED_FLOW_TEST_ID]
    if unapproved:
        errors.append(f"unapproved FLOW-MON-BTC monthly configs found: {unapproved}")

    return errors


def summarize_priorities(
    priorities_path: str | Path = DEFAULT_PRIORITIES_PATH,
    hypotheses_path: str | Path = DEFAULT_HYPOTHESES_PATH,
    live_config_dir: str | Path = DEFAULT_LIVE_CONFIG_DIR,
) -> dict[str, Any]:
    priorities = load_priorities(priorities_path)
    signals = priorities["signals"]
    cross = signals[CROSS_ASSET_ID]
    flow = signals[FLOW_MONTH_ID]
    errors = validate_priorities(priorities_path, hypotheses_path, live_config_dir)
    return {
        "decision_id": priorities["decision_id"],
        "as_of": priorities["as_of"],
        "highest_priority": CROSS_ASSET_ID,
        "highest_priority_status": cross["status"],
        "highest_priority_live_launch_authorized": cross["live_launch_authorized"],
        "highest_priority_blockers": cross["current_blockers"],
        "monthly_flow_priority_tier": flow["priority_tier"],
        "monthly_flow_current_test": flow["current_one_off_test_id"],
        "monthly_flow_future_launches_enabled": flow["future_month_launches_enabled"],
        "monthly_flow_post_test_status": flow["post_current_test_status"],
        "discovered_monthly_flow_configs": discover_flow_month_configs(live_config_dir),
        "real_money_trading_authorized": False,
        "valid": not errors,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and summarize signal research priorities")
    parser.add_argument("--priorities", default=str(DEFAULT_PRIORITIES_PATH))
    parser.add_argument("--hypotheses", default=str(DEFAULT_HYPOTHESES_PATH))
    parser.add_argument("--live-config-dir", default=str(DEFAULT_LIVE_CONFIG_DIR))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    summary = summarize_priorities(args.priorities, args.hypotheses, args.live_config_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.validate and not summary["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
