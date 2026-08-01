import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_research.live_flow_mon_btc import (
    calculate_performance,
    execution_observation,
    mark_schedule,
    parse_utc,
    update_record,
    validate_static,
)


UTC = timezone.utc


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        for suffix, payload in self.routes:
            if url.endswith(suffix):
                value = payload(params or {}) if callable(payload) else payload
                return FakeResponse(value)
        return FakeResponse({"error": "unmatched route"}, status_code=404)


class LiveFlowMonBtcTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            Path("signal_research/live_tests/FLOW-MON-BTC-2026-08.json").read_text(
                encoding="utf-8"
            )
        )
        self.record = json.loads(
            Path("signal_records/live/FLOW-MON-BTC-2026-08.json").read_text(
                encoding="utf-8"
            )
        )

    def test_committed_static_definition_is_valid(self):
        self.assertEqual([], validate_static(self.config, self.record))
        self.assertEqual(
            datetime(2026, 8, 1, 0, 5, tzinfo=UTC),
            parse_utc(self.config["entry_timestamp_utc"]),
        )
        self.assertFalse(self.config["real_money_trading_authorized"])
        self.assertEqual("untouched_out_of_sample_shadow", self.config["test_type"])

    def test_mark_schedule_excludes_entry_and_exit(self):
        entry = datetime(2026, 8, 1, 0, 5, tzinfo=UTC)
        exit_ = datetime(2026, 8, 8, 0, 5, tzinfo=UTC)
        as_of = datetime(2026, 8, 5, 1, 0, tzinfo=UTC)
        schedule = mark_schedule(entry, exit_, as_of)
        self.assertEqual(4, len(schedule))
        self.assertEqual(datetime(2026, 8, 2, 0, 5, tzinfo=UTC), schedule[0])
        self.assertEqual(datetime(2026, 8, 5, 0, 5, tzinfo=UTC), schedule[-1])

    def test_execution_uses_earliest_aggregate_trade(self):
        session = FakeSession(
            [
                (
                    "/fapi/v1/aggTrades",
                    [
                        {"a": 11, "p": "101.0", "q": "0.5", "T": 1785542700500, "m": False},
                        {"a": 10, "p": "100.0", "q": "0.3", "T": 1785542700100, "m": True},
                    ],
                )
            ]
        )
        observation = execution_observation(
            session,
            self.config,
            datetime(2026, 8, 1, 0, 5, tzinfo=UTC),
        )
        self.assertEqual(100.0, observation["price"])
        self.assertEqual(10, observation["aggregate_trade_id"])
        self.assertEqual(
            "earliest_public_aggregate_trade_at_or_after_timestamp",
            observation["source_method"],
        )

    def test_execution_falls_back_to_kline_open(self):
        session = FakeSession(
            [
                ("/fapi/v1/aggTrades", []),
                (
                    "/fapi/v1/klines",
                    [[1785542700000, "99.5", "101", "99", "100", "1", 1785542759999]],
                ),
            ]
        )
        observation = execution_observation(
            session,
            self.config,
            datetime(2026, 8, 1, 0, 5, tzinfo=UTC),
        )
        self.assertEqual(99.5, observation["price"])
        self.assertEqual("one_minute_kline_open_at_timestamp", observation["source_method"])

    def test_update_record_opens_and_marks_shadow(self):
        def trades(params):
            target = int(params["startTime"])
            day_offset = (target - 1785542700000) // 86_400_000
            price = 100_000.0 + day_offset * 1_000.0
            return [
                {
                    "a": 100 + day_offset,
                    "p": str(price),
                    "q": "0.01",
                    "T": target + 50,
                    "m": False,
                }
            ]

        session = FakeSession(
            [
                (
                    "/fapi/v1/exchangeInfo",
                    {
                        "symbols": [
                            {
                                "symbol": "BTCUSDT",
                                "contractType": "PERPETUAL",
                                "status": "TRADING",
                                "quoteAsset": "USDT",
                                "marginAsset": "USDT",
                            }
                        ]
                    },
                ),
                ("/fapi/v1/aggTrades", trades),
                (
                    "/fapi/v1/fundingRate",
                    [
                        {
                            "fundingTime": 1785571200000,
                            "fundingRate": "0.0001",
                            "markPrice": "100500.0",
                        }
                    ],
                ),
            ]
        )
        updated = update_record(
            self.config,
            json.loads(json.dumps(self.record)),
            session,
            datetime(2026, 8, 3, 1, 0, tzinfo=UTC),
        )
        self.assertEqual("open", updated["status"])
        self.assertEqual(100000.0, updated["entry"]["price"])
        self.assertEqual(2, len(updated["marks"]))
        self.assertEqual(1, len(updated["funding_observations"]))
        self.assertFalse(updated["performance"]["closed"])
        self.assertFalse(updated["real_money_trading_authorized"])
        self.assertTrue(updated["record_fingerprint"])

    def test_performance_separates_gross_funding_and_execution_costs(self):
        record = {
            "entry": {"price": 100.0, "target_timestamp_utc": "2026-08-01T00:05:00Z"},
            "marks": [
                {"price": 110.0, "target_timestamp_utc": "2026-08-02T00:05:00Z"}
            ],
            "funding_observations": [
                {"long_position_cash_flow_usdt": -0.1}
            ],
            "exit": None,
        }
        result = calculate_performance(self.config, record)
        self.assertAlmostEqual(0.10, result["gross_return"])
        self.assertAlmostEqual(-0.001, result["cumulative_funding_return"])
        self.assertAlmostEqual(-0.0014, result["assumed_round_trip_execution_cost_return"])
        self.assertAlmostEqual(0.0976, result["estimated_after_cost_return_if_closed"])

    def test_static_validation_rejects_real_money_authorization(self):
        bad = json.loads(json.dumps(self.config))
        bad["real_money_trading_authorized"] = True
        errors = validate_static(bad, self.record)
        self.assertTrue(any("prohibit real-money trading" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
