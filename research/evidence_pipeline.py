"""Evidence-first market observation intake. Read-only; never submits orders."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MarketObservation:
    source_id: str
    event_time: datetime
    received_at: datetime
    symbol: str
    timeframe: str
    values: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name, value in (("event_time", self.event_time), ("received_at", self.received_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if not self.source_id.strip() or not self.symbol.strip() or not self.timeframe.strip():
            raise ValueError("source_id, symbol and timeframe are required")
        if self.schema_version != 1:
            raise ValueError("unsupported observation schema version")
        # Ensure values are canonical JSON data, not objects with unstable repr().
        json.dumps(self.values, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @property
    def content_hash(self) -> str:
        body = {
            "source_id": self.source_id,
            "event_time": self.event_time.astimezone(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "values": self.values,
            "schema_version": self.schema_version,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IngestResult:
    accepted: bool
    duplicate: bool
    out_of_order: bool
    stale: bool
    clock_skew: bool
    content_hash: str
    provenance: str = "candidate_unverified"
    evidence_eligible: bool = False


class ResearchEvidencePipeline:
    """Durable intake and quality reporting; authenticity is never self-attested."""

    def __init__(self, database: str | Path, *, max_age_seconds: int = 120,
                 max_future_skew_seconds: int = 5) -> None:
        if max_age_seconds < 0 or max_future_skew_seconds < 0:
            raise ValueError("time tolerances must be non-negative")
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self.max_age_seconds = max_age_seconds
        self.max_future_skew_seconds = max_future_skew_seconds
        with self._session() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS market_observations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL UNIQUE,
                    source_id TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    out_of_order INTEGER NOT NULL,
                    stale INTEGER NOT NULL,
                    clock_skew INTEGER NOT NULL,
                    provenance TEXT NOT NULL CHECK(provenance = 'candidate_unverified')
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS market_source_time_idx
                ON market_observations(source_id, event_time)
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def _session(self):
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, observation: MarketObservation, *, now: datetime | None = None) -> IngestResult:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        event_time = observation.event_time.astimezone(timezone.utc)
        received_at = observation.received_at.astimezone(timezone.utc)
        now = now.astimezone(timezone.utc)
        age = (now - event_time).total_seconds()
        stale = age > self.max_age_seconds
        clock_skew = age < -self.max_future_skew_seconds or (received_at - now).total_seconds() > self.max_future_skew_seconds
        with self._session() as db:
            duplicate = db.execute(
                "SELECT 1 FROM market_observations WHERE content_hash = ?",
                (observation.content_hash,),
            ).fetchone() is not None
            if duplicate:
                return IngestResult(False, True, False, stale, clock_skew, observation.content_hash)
            previous = db.execute(
                "SELECT MAX(event_time) FROM market_observations WHERE source_id = ? AND symbol = ? AND timeframe = ?",
                (observation.source_id, observation.symbol, observation.timeframe),
            ).fetchone()[0]
            out_of_order = previous is not None and event_time.isoformat() < previous
            db.execute("""
                INSERT INTO market_observations
                (content_hash, source_id, event_time, received_at, symbol, timeframe,
                 values_json, out_of_order, stale, clock_skew, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate_unverified')
            """, (
                observation.content_hash, observation.source_id, event_time.isoformat(),
                received_at.isoformat(), observation.symbol, observation.timeframe,
                json.dumps(observation.values, sort_keys=True, separators=(",", ":"), allow_nan=False),
                int(out_of_order), int(stale), int(clock_skew),
            ))
        return IngestResult(True, False, out_of_order, stale, clock_skew, observation.content_hash)


    def source_health_report(
        self,
        source_id: str,
        *,
        expected_interval_seconds: int,
        outage_after_seconds: int,
        now: datetime | None = None,
    ):
        """Build cadence diagnostics from persisted observations for one source."""
        from research.source_health import SourceEvent, assess_source_health

        now = now or datetime.now(timezone.utc)
        with self._session() as db:
            rows = db.execute(
                """
                SELECT event_time, out_of_order, stale, clock_skew
                FROM market_observations
                WHERE source_id = ?
                ORDER BY event_time
                """,
                (source_id,),
            ).fetchall()
        events = [
            SourceEvent(
                source_id=source_id,
                event_time=datetime.fromisoformat(row[0]),
                out_of_order=bool(row[1]),
                stale=bool(row[2]),
                clock_skew=bool(row[3]),
            )
            for row in rows
        ]
        return assess_source_health(
            source_id,
            events,
            expected_interval_seconds=expected_interval_seconds,
            outage_after_seconds=outage_after_seconds,
            now=now,
        )

    def report(self, *, source_id: str | None = None) -> dict[str, Any]:
        query = "SELECT COUNT(*), SUM(out_of_order), SUM(stale), SUM(clock_skew), COUNT(DISTINCT content_hash) FROM market_observations"
        args: tuple[Any, ...] = ()
        if source_id is not None:
            query += " WHERE source_id = ?"
            args = (source_id,)
        with self._session() as db:
            count, out_of_order, stale, skew, unique = db.execute(query, args).fetchone()
            sources = db.execute(
                "SELECT DISTINCT source_id FROM market_observations" + (" WHERE source_id = ?" if source_id else "") + " ORDER BY source_id",
                args,
            ).fetchall()
        return {
            "observations": count,
            "unique_observations": unique,
            "out_of_order": out_of_order or 0,
            "stale": stale or 0,
            "clock_skew": skew or 0,
            "sources": [row[0] for row in sources],
            "provenance": "candidate_unverified",
            "verified_observations": 0,
            "evidence_eligible": False,
            "status": "INSUFFICIENT_EVIDENCE",
        }


def validate_forecast_window(*, decision_at: datetime, outcome_start: datetime,
                             outcome_end: datetime) -> None:
    """Reject temporal leakage: the decision must precede the entire outcome window."""
    values = (decision_at, outcome_start, outcome_end)
    if any(v.tzinfo is None or v.utcoffset() is None for v in values):
        raise ValueError("forecast timestamps must be timezone-aware")
    decision_at, outcome_start, outcome_end = (v.astimezone(timezone.utc) for v in values)
    if outcome_end <= outcome_start:
        raise ValueError("outcome window must have positive duration")
    if decision_at >= outcome_start:
        raise ValueError("forecast decision must precede outcome window")
