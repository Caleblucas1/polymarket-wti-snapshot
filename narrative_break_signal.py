#!/usr/bin/env python3
"""Classify Iran de-escalation narrative-break scenarios.

The module is intentionally rule-first: each signal component can be mixed into
an artificial or real scenario, then classified into the daily briefing language.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class Move(str, Enum):
    UP = "up"
    SLIGHTLY_UP = "slightly_up"
    STABLE = "stable"
    FLAT = "flat"
    DOWN = "down"
    HARD_DOWN = "hard_down"
    MISSING = "missing"


class Level(str, Enum):
    GREEN = "Green"
    WEAKER_YELLOW = "Weaker Yellow"
    YELLOW = "Yellow"
    YELLOW_ORANGE = "Yellow/Orange"
    ORANGE = "Orange"
    ORANGE_RED = "Orange/Red"
    RED = "Red"


@dataclass(frozen=True)
class SignalResult:
    level: Level
    interpretation: str
    matched_rules: tuple[str, ...]
    score: int
    missing_components: tuple[str, ...]


COMPONENTS = {
    "peace_talk_near_term": "Near-term U.S.-Iran peace-talk odds, such as Aug 31.",
    "peace_talk_long_term": "Later peace-talk odds, such as December or year-end if available.",
    "blockade_near_term": "Near-term U.S. blockade-end odds, such as Aug 15 or Aug 31.",
    "blockade_intermediate": "Middle of the curve between August and year-end, if available.",
    "blockade_long_term": "Long-dated U.S. blockade-end odds, such as December/year-end.",
    "shipping_risk": "Bab el-Mandeb, Houthi, or similar second-chokepoint risk odds.",
    "hormuz_normalization": "Hormuz reopening or transit-normalization odds.",
    "wti_upside_threshold": "WTI/Brent upside-threshold odds such as $90, $100, $110, or $120.",
}


MOVE_HELP = ", ".join(move.value for move in Move)


def normalize_move(value: Any) -> Move:
    if value is None or value == "":
        return Move.MISSING
    if isinstance(value, Move):
        return value
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "higher": Move.UP,
        "rising": Move.UP,
        "rise": Move.UP,
        "clear_up": Move.UP,
        "clearly_up": Move.UP,
        "slight_up": Move.SLIGHTLY_UP,
        "slightly_higher": Move.SLIGHTLY_UP,
        "unchanged": Move.STABLE,
        "firm": Move.STABLE,
        "mostly_flat": Move.FLAT,
        "lower": Move.DOWN,
        "falling": Move.DOWN,
        "fall": Move.DOWN,
        "drops": Move.DOWN,
        "drop": Move.DOWN,
        "hard_lower": Move.HARD_DOWN,
        "falls_hard": Move.HARD_DOWN,
        "unknown": Move.MISSING,
        "na": Move.MISSING,
        "n/a": Move.MISSING,
    }
    if text in aliases:
        return aliases[text]
    try:
        return Move(text)
    except ValueError as exc:
        raise ValueError(f"Unknown move {value!r}. Use one of: {MOVE_HELP}") from exc


def is_down(move: Move) -> bool:
    return move in {Move.DOWN, Move.HARD_DOWN}


def is_stable(move: Move) -> bool:
    return move in {Move.STABLE, Move.FLAT}


def is_up(move: Move) -> bool:
    return move in {Move.UP, Move.SLIGHTLY_UP}


def classify_scenario(raw_scenario: dict[str, Any]) -> SignalResult:
    scenario = {name: normalize_move(raw_scenario.get(name)) for name in COMPONENTS}
    missing = tuple(name for name, move in scenario.items() if move == Move.MISSING)

    peace_near = scenario["peace_talk_near_term"]
    peace_long = scenario["peace_talk_long_term"]
    blockade_near = scenario["blockade_near_term"]
    blockade_mid = scenario["blockade_intermediate"]
    blockade_long = scenario["blockade_long_term"]
    shipping = scenario["shipping_risk"]
    hormuz = scenario["hormuz_normalization"]
    wti = scenario["wti_upside_threshold"]

    matched: list[str] = []
    score = 0

    if is_down(peace_near):
        matched.append("Near-term peace-talk odds are falling.")
        score += 1
    if is_down(blockade_near):
        matched.append("Near-term blockade-end odds are falling.")
        score += 1
    if is_down(peace_long) or is_down(blockade_long):
        matched.append("Long-dated de-escalation odds are falling.")
        score += 2
    if is_down(blockade_mid):
        matched.append("Intermediate blockade-curve odds are falling.")
        score += 1
    if is_up(shipping):
        matched.append("Shipping-risk markets are rising.")
        score += 2
    if is_down(hormuz):
        matched.append("Hormuz or transit-normalization odds are weakening.")
        score += 2
    if wti == Move.SLIGHTLY_UP:
        matched.append("WTI upside-threshold odds are only slightly higher.")
        score += 1
    elif wti == Move.UP:
        matched.append("WTI upside-threshold odds are clearly higher.")
        score += 2

    if all(is_stable(scenario[name]) for name in COMPONENTS if scenario[name] != Move.MISSING):
        return SignalResult(
            Level.GREEN,
            "De-escalation narrative intact; no component is confirming a break.",
            ("All provided components are stable or flat.",),
            0,
            missing,
        )

    if (
        is_down(peace_near)
        and not is_down(blockade_near)
        and is_stable(blockade_long)
        and (peace_long == Move.MISSING or is_stable(peace_long))
    ):
        return SignalResult(
            Level.WEAKER_YELLOW,
            (
                "Peace-talk timing is weakening, but near-term blockade odds and the "
                "long-dated curve are not confirming it."
            ),
            tuple(matched)
            + (
                "Long-dated stability weakens the warning only because near-term blockade odds did not fall.",
            ),
            score,
            missing,
        )

    if (
        is_down(peace_near)
        and is_down(blockade_near)
        and is_stable(blockade_long)
        and is_stable(shipping)
        and wti in {Move.SLIGHTLY_UP, Move.STABLE, Move.FLAT, Move.MISSING}
        and (peace_long == Move.MISSING or is_stable(peace_long))
    ):
        return SignalResult(
            Level.YELLOW,
            (
                "Near-term resolution is being pushed later, but physical-risk markets "
                "are flat and oil upside is not strongly confirming the move."
            ),
            tuple(matched)
            + (
                "This matches the calibrated Question 2 rule: near-term drop, long-term stable, weak confirmation.",
            ),
            score,
            missing,
        )

    if is_down(peace_near) and is_down(blockade_near) and is_stable(blockade_long):
        return SignalResult(
            Level.YELLOW_ORANGE,
            (
                "The near-term normalization narrative is weakening, but long-dated "
                "resolution odds still imply eventual de-escalation."
            ),
            tuple(matched),
            score,
            missing,
        )

    if score >= 7:
        level = Level.RED
        interpretation = (
            "Narrative deterioration and physical or oil-market confirmation are moving "
            "together; this is a strong bullish oil warning."
        )
    elif score >= 5:
        level = Level.ORANGE
        interpretation = (
            "Multiple components are confirming deterioration; the fakeout risk is becoming real."
        )
    elif score >= 4:
        level = Level.YELLOW_ORANGE
        interpretation = "The signal is stronger than Yellow, but not yet a full break."
    elif score >= 2:
        level = Level.YELLOW
        interpretation = "There is a timing-risk warning, but confirmation is limited."
    else:
        level = Level.GREEN
        interpretation = "The de-escalation narrative remains broadly intact."

    return SignalResult(level, interpretation, tuple(matched), score, missing)


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def result_to_dict(result: SignalResult) -> dict[str, Any]:
    return {
        "level": result.level.value,
        "interpretation": result.interpretation,
        "matched_rules": list(result.matched_rules),
        "score": result.score,
        "missing_components": list(result.missing_components),
    }


def print_components() -> None:
    print("Signal components")
    for name, description in COMPONENTS.items():
        print(f"- {name}: {description}")
    print(f"\nAllowed moves: {MOVE_HELP}")


def ask_move(name: str, description: str) -> Move:
    while True:
        answer = input(f"{name} ({description}) [{MOVE_HELP}]: ").strip()
        try:
            return normalize_move(answer or Move.MISSING)
        except ValueError as exc:
            print(exc)


def run_questionnaire() -> dict[str, str]:
    print("Narrative Break Signal game")
    print("Mix the market components, then I will classify the scenario.\n")
    return {name: ask_move(name, description).value for name, description in COMPONENTS.items()}


def print_result(result: SignalResult, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result_to_dict(result), indent=2))
        return
    print(f"Signal: {result.level.value}")
    print(f"Score: {result.score}")
    print(result.interpretation)
    if result.matched_rules:
        print("\nMatched rules:")
        for rule in result.matched_rules:
            print(f"- {rule}")
    if result.missing_components:
        print("\nMissing components:")
        for component in result.missing_components:
            print(f"- {component}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify Iran de-escalation narrative-break signal scenarios."
    )
    parser.add_argument("--scenario-json", help="Path to a JSON object of component moves.")
    parser.add_argument("--json", action="store_true", help="Print result as JSON.")
    parser.add_argument(
        "--list-components",
        action="store_true",
        help="Show component names and allowed move values.",
    )
    for component in COMPONENTS:
        parser.add_argument(f"--{component.replace('_', '-')}", choices=[m.value for m in Move])
    return parser


def scenario_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.scenario_json:
        return load_scenario(args.scenario_json)
    scenario = {
        component: getattr(args, component)
        for component in COMPONENTS
        if getattr(args, component) is not None
    }
    if scenario:
        return scenario
    return run_questionnaire()


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_components:
        print_components()
        return 0
    try:
        result = classify_scenario(scenario_from_args(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print_result(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
