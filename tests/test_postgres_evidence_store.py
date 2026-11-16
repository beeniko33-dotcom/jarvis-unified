from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from research.evidence_pipeline import MarketObservation
from research.postgres_evidence_store import PostgresEvidenceStore


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        if "pg_advisory_xact_lock" in normalized:
            self.result = (None,)
        elif "select max(event_time)" in normalized:
            matches = [
                row["event_time"] for row in self.state["rows"]
                if (row["source_id"], row["symbol"], row["timeframe"])
                == tuple(params)
            ]
            self.result = (max(matches) if matches else None,)
        elif normalized.startswith("insert into jarvis_private.market_observations"):
            source, event, received, symbol, timeframe, version, digest, values, ordered, stale, skew = params
            if any(r["source_id"] == source and r["content_hash"] == digest for r in self.state["rows"]):
                self.result = None
            else:
                self.state["rows"].append({
                    "source_id": source, "event_time": event, "received_at": received,
                    "symbol": symbol, "timeframe": timeframe, "schema_version": version,
                    "content_hash": digest, "values_json": values,
                    "out_of_order": ordered, "stale": stale, "clock_skew": skew,
                })
                self.result = (ordered,)
        elif normalized.startswith("select count(*)"):
            rows = [r for r in self.state["rows"] if params[0] is None or r["source_id"] == params[0]]
            self.result = (
                len(rows), sum(bool(r["out_of_order"]) for r in rows),
                sum(bool(r["stale"]) for r in rows), sum(bool(r["clock_skew"]) for r in rows),
                len({r["content_hash"] for r in rows}),
            )
        elif normalized.startswith("select distinct source_id"):
            rows = sorted({r["source_id"] for r in self.state["rows"] if params[0] is None or r["source_id"] == params[0]})
            self.result = [(r,) for r in rows]
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class FakeConnection:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return FakeCursor(self)


class PostgresEvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.state = {"rows": []}
        self.store = PostgresEvidenceStore(
            "postgresql://fake",
            connection_factory=lambda: FakeConnection(self.state),
            max_age_seconds=120,
        )
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)

    def observation(self, minute, *, value=1):
        event = self.now + timedelta(minutes=minute)
        return MarketObservation(
            source_id="feed-a", event_time=event, received_at=event,
            symbol="EURUSD", timeframe="1m", values={"close": value},
        )

    def test_ingest_and_duplicate_are_idempotent(self):
        first = self.store.ingest(self.observation(0), now=self.now)
        again = self.store.ingest(self.observation(0), now=self.now)
        self.assertTrue(first.accepted)
        self.assertFalse(first.duplicate)
        self.assertFalse(again.accepted)
        self.assertTrue(again.duplicate)
        self.assertEqual(len(self.state["rows"]), 1)

    def test_out_of_order_is_detected(self):
        self.store.ingest(self.observation(1), now=self.now + timedelta(minutes=1))
        older = self.store.ingest(self.observation(0), now=self.now + timedelta(minutes=1))
        self.assertTrue(older.accepted)
        self.assertTrue(older.out_of_order)

    def test_stale_and_future_skew_are_reported(self):
        stale = self.store.ingest(self.observation(-10), now=self.now)
        future = self.store.ingest(self.observation(10), now=self.now)
        self.assertTrue(stale.stale)
        self.assertTrue(future.clock_skew)

    def test_report_preserves_unverified_provenance(self):
        self.store.ingest(self.observation(0), now=self.now)
        report = self.store.report()
        self.assertEqual(report["observations"], 1)
        self.assertEqual(report["provenance"], "candidate_unverified")
        self.assertFalse(report["evidence_eligible"])

    def test_requires_a_dsn_or_connection_factory(self):
        with self.assertRaisesRegex(ValueError, "JARVIS_DATABASE_URL"):
            PostgresEvidenceStore("")
