import io
import json
import sys
import types
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.modules.setdefault("requests", types.SimpleNamespace(Session=object))

from signal_research.live_flow_mon_btc_resilient import (
    archive_execution_observation,
    archive_url,
    collect_resilient,
)


UTC = timezone.utc


def fresh_record() -> dict:
    """Frozen pre-observation fixture; the committed live record is intentionally mutable."""
    return {
        "schema_version": 1,
        "live_test_id": "FLOW-MON-BTC-2026-08",
        "registry_id": "FLOW-MON-BTC-001",
        "status": "awaiting_snapshot",
        "test_type": "untouched_out_of_sample_shadow",
        "real_money_trading_authorized": False,
        "entry": None,
        "marks": [],
        "funding_observations": [],
        "exit": None,
        "performance": None,
        "last_updated_at_utc": None,
        "data_quality": {
            "source": "Binance USD-M Futures public REST API",
            "complete": False,
            "errors": [],
        },
        "notes": "Deterministic test fixture for the frozen shadow collector.",
    }


class FakeResponse:
    def __init__(self, status_code, *, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, api_status=451, archive_content=None):
        self.api_status = api_status
        self.archive_content = archive_content
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if url.endswith("/fapi/v1/exchangeInfo"):
            return FakeResponse(
                self.api_status,
                payload={"code": 0, "msg": "Service unavailable from a restricted location"},
            )
        if "data.binance.vision" in url:
            if self.archive_content is None:
                return FakeResponse(404, text="not published")
            return FakeResponse(200, content=self.archive_content)
        return FakeResponse(404, text="unmatched")


def make_zip(rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        body = "\n".join(",".join(str(value) for value in row) for row in rows) + "\n"
        archive.writestr("BTCUSDT-aggTrades-2026-08-01.csv", body)
    return buffer.getvalue()


class ResilientFlowMonBtcTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            Path("signal_research/live_tests/FLOW-MON-BTC-2026-08.json").read_text(
                encoding="utf-8"
            )
        )
        self.record = fresh_record()

    def test_archive_url_is_bound_to_frozen_date(self):
        target = datetime(2026, 8, 1, 0, 5, tzinfo=UTC)
        self.assertEqual(
            "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-08-01.zip",
            archive_url("BTCUSDT", target),
        )

    def test_archive_observation_uses_earliest_eligible_trade(self):
        content = make_zip(
            [
                ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"],
                [101, "100100.0", "0.01", 201, 201, 1785542700500, "false"],
                [100, "100000.0", "0.02", 200, 200, 1785542700100, "true"],
            ]
        )
        observation = archive_execution_observation(
            FakeSession(archive_content=content),
            "BTCUSDT",
            datetime(2026, 8, 1, 0, 5, tzinfo=UTC),
        )
        self.assertEqual(100000.0, observation["price"])
        self.assertEqual(100, observation["aggregate_trade_id"])
        self.assertEqual(
            "binance_public_archive_earliest_aggregate_trade",
            observation["source_method"],
        )
        self.assertTrue(observation["archive_zip_sha256"])

    def test_same_day_451_becomes_honest_pending_archive_state(self):
        updated = collect_resilient(
            self.config,
            json.loads(json.dumps(self.record)),
            FakeSession(api_status=451, archive_content=None),
            datetime(2026, 8, 1, 6, 30, tzinfo=UTC),
        )
        self.assertEqual("awaiting_official_archive", updated["status"])
        self.assertIsNone(updated["entry"])
        self.assertEqual(
            ["2026-08-01T00:05:00Z"],
            updated["data_quality"]["pending_target_timestamps_utc"],
        )
        self.assertTrue(updated["data_quality"]["archive_publication_lag"])
        self.assertFalse(updated["real_money_trading_authorized"])

    def test_next_day_archive_backfills_original_timestamp(self):
        content = make_zip(
            [
                [100, "99999.0", "0.01", 200, 200, 1785542699900, "false"],
                [101, "100123.4", "0.01", 201, 201, 1785542700050, "false"],
            ]
        )
        updated = collect_resilient(
            self.config,
            json.loads(json.dumps(self.record)),
            FakeSession(api_status=451, archive_content=content),
            datetime(2026, 8, 2, 6, 30, tzinfo=UTC),
        )
        self.assertEqual("open_archive_lagged", updated["status"])
        self.assertEqual("2026-08-01T00:05:00Z", updated["entry"]["target_timestamp_utc"])
        self.assertEqual(100123.4, updated["entry"]["price"])
        self.assertEqual("pending_official_monthly_archive", updated["funding_status"])
        self.assertFalse(updated["performance"]["funding_complete"])
        self.assertIsNone(updated["performance"]["estimated_after_cost_return_if_closed"])


if __name__ == "__main__":
    unittest.main()
