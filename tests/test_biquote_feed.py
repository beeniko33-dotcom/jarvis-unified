import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.biquote_feed import (
    BIQUOTE_HUB, PROVIDER, build_tick_observation, collection_exit_code,
)


class BiquoteFeedTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.tick = {
            "symbol": "EURUSD",
            "bid": 1.08542,
            "ask": 1.08548,
            "mid": 1.08545,
            "timestamp": "2026-11-14T11:59:59Z",
            "source": "MetaTrader 5 (Broker 1)",
            "marketState": "open",
            "stale": False,
            "quoteAgeSeconds": 1,
        }

    def build(self, tick=None, received=None):
        return build_tick_observation(
            self.tick if tick is None else tick,
            received_at=self.now if received is None else received,
        )

    def test_valid_quote_is_candidate_only_and_preserves_raw_payload(self):
        item = self.build()
        self.assertEqual(item["provider"], PROVIDER)
        self.assertEqual(item["instrument"], "EURUSD")
        self.assertEqual(item["trust_classification"], "candidate_unverified")
        self.assertFalse(item["evidence_credit"])
        self.assertFalse(item["provenance_verified"])
        self.assertEqual(item["bid"], "1.08542")
        self.assertEqual(item["ask"], "1.08548")
        self.assertEqual(item["mid"], "1.08545")
        self.assertIn('"symbol":"EURUSD"', item["raw_payload"])
        self.assertEqual(len(item["raw_payload_sha256"]), 64)

    def test_rejects_wrong_symbol_and_missing_source(self):
        wrong = dict(self.tick, symbol="GBPUSD")
        with self.assertRaisesRegex(ValueError, "symbol"):
            self.build(wrong)
        missing = dict(self.tick)
        del missing["source"]
        with self.assertRaisesRegex(ValueError, "source"):
            self.build(missing)

    def test_rejects_stale_closed_and_missing_stale_flag(self):
        for changes in (
            {"stale": True},
            {"stale": None},
            {"marketState": "closed"},
            {"quoteAgeSeconds": 121},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.build(dict(self.tick, **changes))

    def test_rejects_invalid_quote_fields(self):
        for changes in (
            {"bid": 0},
            {"ask": 0},
            {"mid": 0},
            {"ask": 1.08540},
            {"mid": 1.09000},
            {"quoteAgeSeconds": -1},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.build(dict(self.tick, **changes))

    def test_rejects_bad_timestamp_future_and_naive_timestamp(self):
        for timestamp in ("not-a-date", "2026-11-14T11:59:59", "2026-11-14T12:01:00Z"):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.build(dict(self.tick, timestamp=timestamp))

    def test_rejects_naive_receive_clock(self):
        with self.assertRaisesRegex(ValueError, "receive time"):
            self.build(received=datetime(2026, 11, 14, 12, 0))

    def test_candidate_cannot_mint_evidence_credit_in_store(self):
        from research.forward_validation import ForwardEvidenceStore

        item = self.build()
        # Caller-supplied trust fields are deliberately present and must be ignored.
        item["provenance_verified"] = True
        item["evidence_credit"] = True
        with tempfile.TemporaryDirectory() as directory:
            store = ForwardEvidenceStore(
                Path(directory) / "candidate.sqlite3",
                instrument="EURUSD",
                provider="Biquote",
                interval="tick",
                strategy_id="sma-crossover-long",
                strategy_version="1.0.0",
                clock=lambda: self.now,
                max_observation_age=timedelta(minutes=2),
            )
            try:
                self.assertTrue(store.ingest(item))
                report = store.report(1)
                self.assertEqual(report["verified_observation_count"], 0)
                self.assertEqual(report["unverified_candidate_count"], 1)
                self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
                self.assertFalse(report["level_3_certification"])
                self.assertTrue(store.verify_chain())
                import json
                stored = json.loads(store.db.execute("SELECT payload FROM observations").fetchone()[0])
                self.assertIs(stored["provenance_verified"], False)
                self.assertIs(stored["evidence_credit"], False)
                self.assertEqual(stored["evidence_class"], "unverified_candidate")
            finally:
                store.close()

    def test_collection_exit_code_rejects_queue_loss_or_rejected_events(self):
        healthy = {
            "event_chain_valid": True, "inserted": 12, "dropped_queue_full": 0,
            "rejected": 0, "collection_integrity": "candidate_observed",
        }
        self.assertEqual(collection_exit_code(healthy), 0)
        for degraded in (
            dict(healthy, dropped_queue_full=1, collection_integrity="degraded"),
            dict(healthy, rejected=1, collection_integrity="degraded"),
            dict(healthy, inserted=0, collection_integrity="no_usable_ticks"),
            dict(healthy, event_chain_valid=False),
        ):
            with self.subTest(degraded=degraded):
                self.assertEqual(collection_exit_code(degraded), 1)

    def test_hub_is_public_https_endpoint(self):
        self.assertEqual(BIQUOTE_HUB, "https://biquote.io/hubs/tick")


if __name__ == "__main__":
    unittest.main()
