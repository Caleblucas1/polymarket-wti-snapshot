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


@dataclass(frozen=True)
class ScenarioCard:
    key: str
    title: str
    expected_level: Level
    scenario: dict[str, Move]
    why: str


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


PRECLASSIFIED_SCENARIOS: tuple[ScenarioCard, ...] = (
    ScenarioCard(
        key="intact-narrative",
        title="De-escalation narrative intact",
        expected_level=Level.GREEN,
        scenario={
            "peace_talk_near_term": Move.STABLE,
            "peace_talk_long_term": Move.STABLE,
            "blockade_near_term": Move.STABLE,
            "blockade_intermediate": Move.STABLE,
            "blockade_long_term": Move.STABLE,
            "shipping_risk": Move.FLAT,
            "hormuz_normalization": Move.STABLE,
            "wti_upside_threshold": Move.FLAT,
        },
        why="Nothing important is confirming a narrative break.",
    ),
    ScenarioCard(
        key="peace-only-drop",
        title="Peace-talk odds fall, rest of curve stable",
        expected_level=Level.WEAKER_YELLOW,
        scenario={
            "peace_talk_near_term": Move.DOWN,
            "peace_talk_long_term": Move.STABLE,
            "blockade_near_term": Move.STABLE,
            "blockade_long_term": Move.STABLE,
            "shipping_risk": Move.FLAT,
            "wti_upside_threshold": Move.FLAT,
        },
        why=(
            "Peace-talk timing is weaker, but near-term blockade odds and long-dated "
            "de-escalation odds do not confirm it."
        ),
    ),
    ScenarioCard(
        key="question-2",
        title="Near-term drop, long-term stable, unmodeled-shock risk",
        expected_level=Level.YELLOW_ORANGE,
        scenario={
            "peace_talk_near_term": Move.DOWN,
            "peace_talk_long_term": Move.STABLE,
            "blockade_near_term": Move.DOWN,
            "blockade_long_term": Move.STABLE,
            "shipping_risk": Move.FLAT,
            "wti_upside_threshold": Move.SLIGHTLY_UP,
        },
        why=(
            "The paired near-term drop in peace talks and blockade resolution implies "
            "something meaningful may have happened in the near-term narrative, even "
            "though shipping risk is flat, long-dated odds are stable, and WTI "
            "upside-threshold odds are only slightly higher."
        ),
    ),
    ScenarioCard(
        key="timing-risk",
        title="Near-term break without physical confirmation",
        expected_level=Level.ORANGE,
        scenario={
            "peace_talk_near_term": Move.DOWN,
            "peace_talk_long_term": Move.STABLE,
            "blockade_near_term": Move.DOWN,
            "blockade_intermediate": Move.DOWN,
            "blockade_long_term": Move.STABLE,
            "shipping_risk": Move.FLAT,
            "wti_upside_threshold": Move.UP,
        },
        why=(
            "Near-term and intermediate timing deteriorate, but long-dated resolution "
            "odds remain stable and physical-risk markets are not yet confirming."
        ),
    ),
    ScenarioCard(
        key="shipping-confirms",
        title="Narrative weakens and shipping risk confirms",
        expected_level=Level.RED,
        scenario={
            "peace_talk_near_term": Move.DOWN,
            "peace_talk_long_term": Move.STABLE,
            "blockade_near_term": Move.DOWN,
            "blockade_long_term": Move.STABLE,
            "shipping_risk": Move.UP,
            "hormuz_normalization": Move.DOWN,
            "wti_upside_threshold": Move.UP,
        },
        why=(
            "Near-term diplomacy and blockade timing weaken while shipping stress and "
            "oil upside odds move in the bullish oil direction."
        ),
    ),
    ScenarioCard(
        key="full-curve-break",
        title="Full de-escalation curve breaks",
        expected_level=Level.RED,
        scenario={
            "peace_talk_near_term": Move.HARD_DOWN,
            "peace_talk_long_term": Move.DOWN,
            "blockade_near_term": Move.HARD_DOWN,
            "blockade_intermediate": Move.DOWN,
            "blockade_long_term": Move.DOWN,
            "shipping_risk": Move.UP,
            "hormuz_normalization": Move.DOWN,
            "wti_upside_threshold": Move.UP,
        },
        why=(
            "This is no longer only a timing shift; the broader resolution story and "
            "physical/oil confirmation layers are deteriorating together."
        ),
    ),
    ScenarioCard(
        key="physical-only-stress",
        title="Physical-risk markets worsen before diplomacy reprices",
        expected_level=Level.ORANGE,
        scenario={
            "peace_talk_near_term": Move.STABLE,
            "peace_talk_long_term": Move.STABLE,
            "blockade_near_term": Move.STABLE,
            "blockade_long_term": Move.STABLE,
            "shipping_risk": Move.UP,
            "hormuz_normalization": Move.DOWN,
            "wti_upside_threshold": Move.SLIGHTLY_UP,
        },
        why=(
            "Shipping and Hormuz stress matter, but diplomacy/blockade odds have not "
            "yet repriced enough to call it a narrative break."
        ),
    ),
)


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
            Level.YELLOW_ORANGE,
            (
                "Near-term resolution is being pushed later. Physical-risk markets are "
                "flat and oil upside is not strongly confirming the move, but the paired "
                "drop in peace-talk and blockade odds may reflect a meaningful near-term "
                "development outside the included model signals."
            ),
            tuple(matched)
            + (
                "This matches the calibrated Question 2 rule: near-term drop, long-term stable, weak confirmation, but possible unmodeled-shock risk.",
            ),
            score,
            missing,
        )

    if (
        is_down(peace_near)
        and is_down(blockade_near)
        and is_stable(blockade_long)
        and not is_up(shipping)
        and not is_down(hormuz)
        and wti != Move.UP
    ):
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


def scenario_cards_by_key() -> dict[str, ScenarioCard]:
    return {card.key: card for card in PRECLASSIFIED_SCENARIOS}


def print_scenarios(*, include_details: bool = False) -> None:
    print("Pre-classified scenario cards")
    for card in PRECLASSIFIED_SCENARIOS:
        print(f"- {card.key}: {card.expected_level.value} - {card.title}")
        if include_details:
            print(f"  Why: {card.why}")
            for component, move in card.scenario.items():
                print(f"  {component}: {move.value}")


def print_scenario_card(card: ScenarioCard, *, as_json: bool = False) -> None:
    result = classify_scenario(card.scenario)
    payload = {
        "key": card.key,
        "title": card.title,
        "expected_level": card.expected_level.value,
        "actual_level": result.level.value,
        "why": card.why,
        "scenario": {name: move.value for name, move in card.scenario.items()},
        "result": result_to_dict(result),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    print(f"{card.key}: {card.title}")
    print(f"Expected: {card.expected_level.value}")
    print(f"Classified: {result.level.value}")
    print(card.why)
    print("\nComponents:")
    for component, move in card.scenario.items():
        print(f"- {component}: {move.value}")
    print("\nClassifier result:")
    print_result(result)


def run_quiz() -> int:
    print("Narrative Break Signal scenario quiz")
    print("Guess the classification before revealing the pre-classified answer.\n")
    correct = 0
    for card in PRECLASSIFIED_SCENARIOS:
        print(f"Scenario: {card.title}")
        for component, move in card.scenario.items():
            print(f"- {component}: {move.value}")
        answer = input("Your classification: ").strip().lower()
        expected = card.expected_level.value.lower()
        if answer == expected:
            correct += 1
            print("Correct.")
        else:
            print(f"Pre-classified as: {card.expected_level.value}")
        print(card.why)
        print()
    print(f"Score: {correct}/{len(PRECLASSIFIED_SCENARIOS)}")
    return correct


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
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Show pre-classified scenario cards.",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(scenario_cards_by_key()),
        help="Classify a pre-built scenario card by key.",
    )
    parser.add_argument(
        "--show-scenario-details",
        action="store_true",
        help="Include component moves when listing scenarios.",
    )
    parser.add_argument(
        "--quiz",
        action="store_true",
        help="Play through the pre-classified scenario cards.",
    )
    for component in COMPONENTS:
        parser.add_argument(f"--{component.replace('_', '-')}", choices=[m.value for m in Move])
    return parser


def scenario_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.scenario:
        return {name: move.value for name, move in scenario_cards_by_key()[args.scenario].scenario.items()}
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
    if args.list_scenarios:
        print_scenarios(include_details=args.show_scenario_details)
        return 0
    if args.quiz:
        run_quiz()
        return 0
    if args.scenario:
        print_scenario_card(scenario_cards_by_key()[args.scenario], as_json=args.json)
        return 0
    try:
        result = classify_scenario(scenario_from_args(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print_result(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
