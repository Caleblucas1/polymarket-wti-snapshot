from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from signal_research.backtest import TradeResult, summarize, summarize_by_regime
from signal_research.confidence import confidence_score
from signal_research.models import ConfidenceEvidence
from signal_research.rebound import ReboundConfig, evaluate_rebound
from signal_research.registry import get_candidate, load_candidates


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def command_list(_: argparse.Namespace) -> None:
    _print_json([
        {"signal_id": item.signal_id, "name": item.name, "stage": item.stage.value, "status": item.status}
        for item in load_candidates()
    ])


def command_show(args: argparse.Namespace) -> None:
    item = get_candidate(args.signal_id)
    payload = asdict(item)
    payload["stage"] = item.stage.value
    _print_json(payload)


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
    parser = argparse.ArgumentParser(description="Signal candidate and research utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List registered signal candidates")
    list_parser.set_defaults(func=command_list)

    show_parser = subparsers.add_parser("show", help="Show one signal specification")
    show_parser.add_argument("signal_id")
    show_parser.set_defaults(func=command_show)

    confidence_parser = subparsers.add_parser("confidence", help="Calculate dynamic evidence confidence")
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
    rebound_parser.add_argument("--prices", required=True, help="Comma-separated prices ending at the decision time")
    rebound_parser.add_argument("--reference", required=True, type=float)
    rebound_parser.add_argument("--lookback", type=int, default=21)
    rebound_parser.add_argument("--reversal-sigma", type=float, default=0.50)
    rebound_parser.add_argument("--trend-window", type=int, default=5)
    rebound_parser.add_argument("--sustain-bars", type=int, default=6)
    rebound_parser.set_defaults(func=command_rebound)

    backtest_parser = subparsers.add_parser("backtest", help="Summarize precomputed trade outcomes")
    backtest_parser.add_argument("--input", required=True, help="JSON array of TradeResult fields")
    backtest_parser.set_defaults(func=command_backtest)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
