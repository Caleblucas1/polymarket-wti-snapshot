import json
import tempfile
import unittest
from pathlib import Path

from signal_review import (
    SIGNAL_DEFINITION_VERSION,
    append_observation,
    apply_user_review,
    build_observation_record,
    level_readthrough,
    oil_readthrough,
    persist_observation,
)
from signal_contracts import (
    ACTIVE_CONTRACT_DEFINITION_VERSION,
    EVENT_SIGNAL_POLICIES,
    contract_signal_metadata,
    exact_contract_key,
    validate_catalog_events,
)


class SignalReviewTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"version": 1, "variables": [{"key": "blockade_long_term"}]}
        self.signals = [
            {
                "key": "blockade_long_term",
                "header": "Iranian blockade ends by Dec. 31 — odds",
                "label": "December 31",
                "current": 87.5,
                "prior_day": 86.0,
                "change_1d": 1.5,
                "change_7d": 2.0,
                "market_move": "up",
                "bullish_direction": "down",
                "oil_readthrough": oil_readthrough(1.5, "down"),
                "level_readthrough": level_readthrough(87.5, "down"),
                "status": "open",
            }
        ]

    def test_higher_long_term_normalization_odds_are_explicitly_oil_bearish(self):
        self.assertIn("oil-bearish", oil_readthrough(1.5, "down"))
        self.assertIn("+1.5 pp", oil_readthrough(1.5, "down"))
        self.assertIn("high normalization probability", level_readthrough(87.5, "down"))

    def test_record_preserves_definition_and_separates_blank_annotation(self):
        record = build_observation_record(
            as_of_et="2026-07-31T14:00:00-04:00",
            signals=self.signals,
            signal_level="mixed / caution",
            catalog=self.catalog,
        )
        self.assertEqual(record["definition_version"], SIGNAL_DEFINITION_VERSION)
        self.assertIsNone(record["signals"][0]["user_rating_vs_prior_day"])
        self.assertEqual(record["signals"][0]["change_1d_pp"], 1.5)

    def test_append_is_idempotent(self):
        record = build_observation_record(
            as_of_et="2026-07-31T14:00:00-04:00",
            signals=self.signals,
            signal_level="mixed / caution",
            catalog=self.catalog,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            self.assertTrue(append_observation(path, record))
            self.assertFalse(append_observation(path, record))
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_persist_observation_is_the_generator_integration_point(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "signal_records" / "observations.jsonl"
            record, appended = persist_observation(
                path,
                as_of_et="2026-07-31T14:00:00-04:00",
                signals=self.signals,
                signal_level="mixed / caution",
                catalog=self.catalog,
            )
            duplicate, appended_again = persist_observation(
                path,
                as_of_et="2026-07-31T14:00:00-04:00",
                signals=self.signals,
                signal_level="mixed / caution",
                catalog=self.catalog,
            )
            self.assertTrue(appended)
            self.assertFalse(appended_again)
            self.assertEqual(record["observation_id"], duplicate["observation_id"])
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_user_review_cannot_change_evidence(self):
        record = build_observation_record(
            as_of_et="2026-07-31T14:00:00-04:00",
            signals=self.signals,
            signal_level="mixed / caution",
            catalog=self.catalog,
        )
        reviewed = apply_user_review(
            record,
            {"blockade_long_term": "more_bearish"},
            {"blockade_long_term": "Higher odds, despite already high level."},
        )
        self.assertEqual(reviewed["signals"][0]["current_probability"], 87.5)
        self.assertEqual(reviewed["signals"][0]["change_1d_pp"], 1.5)
        self.assertEqual(reviewed["signals"][0]["user_rating_vs_prior_day"], "more_bearish")
        self.assertEqual(reviewed["review_status"], "reviewed")

    def test_all_seventeen_supplied_markets_round_trip_as_distinct_evidence(self):
        """Every supplied event remains identifiable in a durable observation.

        The five first-examined contracts are only a highlighted view. The 17
        event pages are the source universe, and each active contract is an
        independent evidence row. This prevents a refactor from silently
        dropping, merging, or renaming a source market.
        """
        catalog = json.loads(
            Path("signal_market_catalog.json").read_text(encoding="utf-8")
        )
        signals = []
        event_items = list(catalog["events"].items())
        for index, (event_id, event) in enumerate(event_items):
            current = 40.0 + index
            prior_day = current - 1.0
            signals.append(
                {
                    "key": event_id,
                    "header": event["label"],
                    "label": event["label"],
                    "current": current,
                    "prior_day": prior_day,
                    "change_1d": current - prior_day,
                    "change_7d": 2.0,
                    "market_move": "up",
                    "bullish_direction": "up",
                    "oil_readthrough": oil_readthrough(1.0, "up"),
                    "level_readthrough": level_readthrough(current, "up"),
                    "status": "open",
                }
            )

        record = build_observation_record(
            as_of_et="2026-07-31T14:00:00-04:00",
            signals=signals,
            signal_level="mixed / caution",
            catalog=catalog,
        )

        self.assertEqual(len(record["signals"]), 17)
        self.assertEqual(
            {signal["key"] for signal in record["signals"]},
            set(catalog["events"]),
        )
        for index, (event_id, event) in enumerate(event_items):
            with self.subTest(event_id=event_id):
                stored = next(
                    signal for signal in record["signals"] if signal["key"] == event_id
                )
                self.assertEqual(stored["header"], event["label"])
                self.assertEqual(stored["current_probability"], 40.0 + index)
                self.assertIsNone(stored["user_rating_vs_prior_day"])
                self.assertIsNone(stored["user_note"])

    def test_full_catalog_observation_is_duplicate_safe(self):
        """The complete 17-market evidence set is still append-only."""
        catalog = json.loads(
            Path("signal_market_catalog.json").read_text(encoding="utf-8")
        )
        signals = [
            {
                "key": event_id,
                "header": event["label"],
                "current": 50.0,
                "prior_day": 49.0,
                "change_1d": 1.0,
                "change_7d": 1.0,
                "market_move": "flat",
                "bullish_direction": "up",
                "oil_readthrough": oil_readthrough(1.0, "up"),
                "level_readthrough": level_readthrough(50.0, "up"),
            }
            for event_id, event in catalog["events"].items()
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            record, appended = persist_observation(
                path,
                as_of_et="2026-07-31T14:00:00-04:00",
                signals=signals,
                signal_level="mixed / caution",
                catalog=catalog,
            )
            duplicate, appended_again = persist_observation(
                path,
                as_of_et="2026-07-31T14:00:00-04:00",
                signals=signals,
                signal_level="mixed / caution",
                catalog=catalog,
            )
            self.assertTrue(appended)
            self.assertFalse(appended_again)
            self.assertEqual(len(record["signals"]), 17)
            self.assertEqual(record["observation_id"], duplicate["observation_id"])
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_every_catalog_event_has_a_direction_policy(self):
        catalog = json.loads(
            Path("signal_market_catalog.json").read_text(encoding="utf-8")
        )
        validate_catalog_events(catalog)
        self.assertEqual(
            set(catalog["events"]),
            set(EVENT_SIGNAL_POLICIES),
        )
        self.assertEqual(
            catalog["definition_version"], ACTIVE_CONTRACT_DEFINITION_VERSION
        )
        self.assertFalse(catalog["contract_policy"]["highlighted_contracts_are_primary"])

    def test_exact_contract_identity_is_not_event_identity(self):
        first = {"conditionId": "condition-1", "groupItemTitle": "August 31"}
        second = {"conditionId": "condition-2", "groupItemTitle": "December 31"}
        self.assertNotEqual(
            exact_contract_key("iran_blockade_ends", first),
            exact_contract_key("iran_blockade_ends", second),
        )
        metadata = contract_signal_metadata("iran_blockade_ends", first)
        self.assertEqual(metadata["signal_scope"], "active_contract")
        self.assertEqual(metadata["event_id"], "iran_blockade_ends")
        self.assertEqual(metadata["contract_id"], "condition-1")
        self.assertEqual(metadata["bullish_direction"], "down")

    def test_observation_preserves_every_contract_identity_and_annotation_boundary(self):
        signals = [
            {
                **contract_signal_metadata(
                    "iran_blockade_ends",
                    {"conditionId": "near", "groupItemTitle": "August 31"},
                ),
                "key": "iran_blockade_ends::near",
                "header": "Iranian blockade ends by August 31",
                "label": "August 31",
                "current": 29.5,
                "prior_day": 39.0,
                "change_1d": -9.5,
                "change_7d": -32.5,
                "market_move": "down",
                "oil_readthrough": oil_readthrough(-9.5, "down"),
                "level_readthrough": level_readthrough(29.5, "down"),
            },
            {
                **contract_signal_metadata(
                    "iran_blockade_ends",
                    {"conditionId": "long", "groupItemTitle": "December 31"},
                ),
                "key": "iran_blockade_ends::long",
                "header": "Iranian blockade ends by December 31",
                "label": "December 31",
                "current": 77.5,
                "prior_day": 88.0,
                "change_1d": -10.5,
                "change_7d": -7.0,
                "market_move": "down",
                "oil_readthrough": oil_readthrough(-10.5, "down"),
                "level_readthrough": level_readthrough(77.5, "down"),
            },
        ]
        record = build_observation_record(
            as_of_et="2026-08-01T09:15:00-04:00",
            signals=signals,
            signal_level="mixed / caution",
            catalog={"events": {"iran_blockade_ends": {}}},
        )
        self.assertEqual(len(record["signals"]), 2)
        self.assertEqual(
            {row["contract_id"] for row in record["signals"]}, {"near", "long"}
        )
        self.assertTrue(all(row["signal_scope"] == "active_contract" for row in record["signals"]))
        self.assertTrue(all(row["user_rating_vs_prior_day"] is None for row in record["signals"]))

    def test_duplicate_exact_contract_rows_are_rejected(self):
        duplicate = dict(self.signals[0])
        with self.assertRaises(ValueError):
            build_observation_record(
                as_of_et="2026-08-01T09:15:00-04:00",
                signals=[self.signals[0], duplicate],
                signal_level="mixed / caution",
                catalog=self.catalog,
            )


if __name__ == "__main__":
    unittest.main()

