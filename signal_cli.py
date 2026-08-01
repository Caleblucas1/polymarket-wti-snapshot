from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from signal_research.backtest import TradeResult, summarize, summarize_by_regime
from signal_research.confidence import confidence_score
from signal_research.governance import (
    capital_rights,
    confidence_band,
    family_health,
    production_gate,
)
from signal_research.hypotheses import (
    get_hypothesis,
    statuses as hypothesis_statuses,
    summarize_statuses,
    validate_hypotheses,
)
from signal_research.models import ConfidenceEvidence
from signal_research.policy_benchmark import (
    get_case as get_policy_case,
    summarize_benchmark,
    validate_benchmark,
)
from signal_research.policy_pilots import (
    get_pilot as get_policy_pilot,
    summarize_pilots,
    validate_pilots,
)
from signal_research.policy_roadmap import summarize_roadmap, validate_roadmap
from signal_research.rebound import ReboundConfig, evaluate_rebound
from signal_research.registry import get_candidate, load_candidates, validate_registry


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def command_list(_: argparse.Namespace) -> None:
    _print_json([
        {
            "registry_id": item.registry_id,
            "legacy_id": item.signal_id,
            "name": item.name,
            "family": item.family,
            "stage": item.stage.value,
            "status": item.operational_status.value,
            "confidence": item.confidence_score,
            "confidence_band": confidence_band(item.confidence_score),
            "capital_rights": capital_rights(item),
        }
        for item in load_candidates()
    ])


def command_show(args: argparse.Namespace) -> None:
    item = get_candidate(args.identifier)
    payload = asdict(item)
    payload["stage"] = item.stage.value
    payload["operational_status"] = item.operational_status.value
    payload["capital_rights"] = capital_rights(item)
    payload["confidence_band"] = confidence_band(item.confidence_score)
    _print_json(payload)


def command_gate(args: argparse.Namespace) -> None:
    item = get_candidate(args.identifier)
    gate = production_gate(item)
    _print_json({
        "registry_id": item.registry_id,
        "current_stage": item.stage.value,
        "current_status": item.operational_status.value,
        "capital_rights": capital_rights(item),
        **asdict(gate),
    })


def command_families(_: argparse.Namespace) -> None:
    _print_json(family_health(load_candidates()))


def command_hypotheses(_: argparse.Namespace) -> None:
    _print_json(summarize_statuses(hypothesis_statuses()))


def command_hypothesis(args: argparse.Namespace) -> None:
    _print_json(get_hypothesis(args.identifier))


def command_policy_benchmark(_: argparse.Namespace) -> None:
    _print_json(summarize_benchmark())


def command_policy_case(args: argparse.Namespace) -> None:
    _print_json(get_policy_case(args.case_id))


def command_policy_pilots(_: argparse.Namespace) -> None:
    _print_json(summarize_pilots())


def command_policy_pilot(args: argparse.Namespace) -> None:
    _print_json(get_policy_pilot(args.case_id))


def command_policy_roadmap(_: argparse.Namespace) -> None:
    _print_json(summarize_roadmap())


def command_validate(_: argparse.Namespace) -> None:
    registry_errors = validate_registry()
    hypothesis_errors = validate_hypotheses()
    policy_benchmark_errors = validate_benchmark()
    policy_pilot_errors = validate_pilots()
    policy_roadmap_errors = validate_roadmap()
    errors = [
        *(f"registry: {error}" for error in registry_errors),
        *(f"hypotheses: {error}" for error in hypothesis_errors),
        *(f"policy_benchmark: {error}" for error in policy_benchmark_errors),
        *(f"policy_pilots: {error}" for error in policy_pilot_errors),
        *(f"policy_roadmap: {error}" for error in policy_roadmap_errors),
    ]
    if errors:
        _print_json({"valid": False, "errors": errors})
        raise SystemExit(1)
    candidates = load_candidates()
    hypothesis_summary = summarize_statuses(hypothesis_statuses())
    policy_summary = summarize_benchmark()
    pilot_summary = summarize_pilots()
    roadmap_summary = summarize_roadmap()
    _print_json({
        "valid": True,
        "signals": len(candidates),
        "production_signals": sum(
            capital_rights(item) == "capped_live" for item in candidates
        ),
        "frozen_canonical_hypotheses": hypothesis_summary["frozen_canonical"],
        "blocked_canonical_hypotheses": hypothesis_summary["blocked_canonical"],
        "dataset_eligible_signals": hypothesis_summary["dataset_eligible"],
        "historical_policy_benchmark": policy_summary,
        "historical_policy_pilots": pilot_summary,
        "policy_roadmap": roadmap_summary,
        "real_money_trading_authorized": False,
    })


def command_confidence(args: argparse.Namespace) -> None:
    evidence = ConfidenceEvidence(
        sample_size=args.sample_size,
        out_of_sample_trades=args.oos_trades,
        out_of_sample_sharpe=args.oos_sharpe,
        regime_coverage=args.regime_coverage,
        implementation_cost_bps=args.cost_bps,
        gross_edge_bps=args.gross_edge_bps,
        decay_risk=args.decay_risk,
        data_quality=args.data_quality,
    )
    _print_json({"confidence_score": confidence_score(evidence), "evidence": asdict(evidence)})


def command_rebound(args: argparse.Namespace) -> None:
    prices = [float(value) for value in args.prices.split(",")]
    config = ReboundConfig(
        volatility_lookback=args.lookback,
        reversal_sigma=args.reversal_sigma,
        trend_window=args.trend_window,
        sustain_bars=args.sustain_bars,
    )
    observation = evaluate_rebound(prices, reference_level=args.reference, config=config)
    _print_json({**asdict(observation), "score": observation.score, "stage": observation.stage})


def command_backtest(args: argparse.Namespace) -> None:
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = [TradeResult(**item) for item in raw]
    payload = {
        "overall": asdict(summarize(rows)),
        "out_of_sample": asdict(summarize(row for row in rows if row.out_of_sample)),
        "by_regime": {key: asdict(value) for key, value in summarize_by_regime(rows).items()},
    }
    _print_json(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Signal registry and research utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List registered signals")
    list_parser.set_defaults(func=command_list)

    show_parser = subparsers.add_parser("show", help="Show one signal specification")
    show_parser.add_argument("identifier", help="Registry ID, legacy ID or alias")
    show_parser.set_defaults(func=command_show)

    gate_parser = subparsers.add_parser("gate", help="Show production-gate failures")
    gate_parser.add_argument("identifier", help="Registry ID, legacy ID or alias")
    gate_parser.set_defaults(func=command_gate)

    families_parser = subparsers.add_parser("families", help="Summarize registry families")
    families_parser.set_defaults(func=command_families)

    hypotheses_parser = subparsers.add_parser(
        "hypotheses", help="Summarize canonical hypothesis freeze status"
    )
    hypotheses_parser.set_defaults(func=command_hypotheses)

    hypothesis_parser = subparsers.add_parser(
        "hypothesis", help="Show one versioned canonical hypothesis"
    )
    hypothesis_parser.add_argument("identifier", help="Registry ID, legacy ID or alias")
    hypothesis_parser.set_defaults(func=command_hypothesis)

    policy_benchmark_parser = subparsers.add_parser(
        "policy-benchmark",
        help="Summarize the blinded historical policy interpretation benchmark",
    )
    policy_benchmark_parser.set_defaults(func=command_policy_benchmark)

    policy_case_parser = subparsers.add_parser(
        "policy-case",
        help="Show one historical policy benchmark case",
    )
    policy_case_parser.add_argument("case_id", help="Historical policy benchmark case ID")
    policy_case_parser.set_defaults(func=command_policy_case)

    policy_pilots_parser = subparsers.add_parser(
        "policy-pilots",
        help="Summarize non-gating retrospective policy pipeline pilots",
    )
    policy_pilots_parser.set_defaults(func=command_policy_pilots)

    policy_pilot_parser = subparsers.add_parser(
        "policy-pilot",
        help="Show one non-gating retrospective policy pilot",
    )
    policy_pilot_parser.add_argument("case_id", help="Policy pilot case ID")
    policy_pilot_parser.set_defaults(func=command_policy_pilot)

    policy_roadmap_parser = subparsers.add_parser(
        "policy-roadmap",
        help="Show the eight-step policy-alpha roadmap and readiness gate",
    )
    policy_roadmap_parser.set_defaults(func=command_policy_roadmap)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate registry, governance and hypothesis invariants"
    )
    validate_parser.set_defaults(func=command_validate)

    confidence_parser = subparsers.add_parser("confidence", help="Calculate empirical evidence confidence")
    confidence_parser.add_argument("--sample-size", type=int, default=0)
    confidence_parser.add_argument("--oos-trades", type=int, default=0)
    confidence_parser.add_argument("--oos-sharpe", type=float)
    confidence_parser.add_argument("--regime-coverage", type=float, default=0.0)
    confidence_parser.add_argument("--cost-bps", type=float)
    confidence_parser.add_argument("--gross-edge-bps", type=float)
    confidence_parser.add_argument("--decay-risk", type=float, default=1.0)
    confidence_parser.add_argument("--data-quality", type=float, default=0.0)
    confidence_parser.set_defaults(func=command_confidence)

    rebound_parser = subparsers.add_parser("rebound", help="Evaluate the four-component rebound definition")
    rebound_parser.add_argument("--prices", required=True)
    rebound_parser.add_argument("--reference", required=True, type=float)
    rebound_parser.add_argument("--lookback", type=int, default=21)
    rebound_parser.add_argument("--reversal-sigma", type=float, default=0.50)
    rebound_parser.add_argument("--trend-window", type=int, default=5)
    rebound_parser.add_argument("--sustain-bars", type=int, default=6)
    rebound_parser.set_defaults(func=command_rebound)

    backtest_parser = subparsers.add_parser("backtest", help="Summarize precomputed trade outcomes")
    backtest_parser.add_argument("--input", required=True)
    backtest_parser.set_defaults(func=command_backtest)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
