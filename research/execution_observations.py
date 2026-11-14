"""Append-only, hash-chained observations for paper execution learning.

This journal is deliberately separate from the broker ledger. It records only
observations supplied by the execution boundary; absent provenance stays null.
It never authorizes orders or changes risk controls.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ObservationConflictError(RuntimeError):
    """An idempotency key was reused for different observation content."""


class ExecutionObservationJournal:
    SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS execution_observations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    schema_version INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def append(
        self,
        *,
        event_id: str,
        event_type: str,
        data: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> str:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type is required")
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        when = occurred_at or datetime.now(timezone.utc)
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("observation timestamp must be timezone-aware")
        timestamp = when.astimezone(timezone.utc).isoformat()
        payload = self._canonical({
            "schema_version": self.SCHEMA_VERSION,
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": timestamp,
            "data": data,
        })
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT payload,event_hash FROM execution_observations WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                if existing:
                    prior = json.loads(existing[0])
                    current = json.loads(payload)
                    # Retry timestamps are naturally different. Idempotency is
                    # defined by event identity, type and observed data, not retry time.
                    if (
                        prior.get("event_type") != current.get("event_type")
                        or prior.get("data") != current.get("data")
                    ):
                        raise ObservationConflictError(
                            "event_id already exists with different event type or data"
                        )
                    db.commit()
                    return existing[1]
                tail = db.execute(
                    "SELECT event_hash FROM execution_observations ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                previous = tail[0] if tail else "GENESIS"
                digest = hashlib.sha256((previous + "|" + payload).encode("utf-8")).hexdigest()
                db.execute(
                    """INSERT INTO execution_observations
                    (event_id,schema_version,occurred_at,event_type,payload,previous_hash,event_hash)
                    VALUES(?,?,?,?,?,?,?)""",
                    (event_id, self.SCHEMA_VERSION, timestamp, event_type, payload, previous, digest),
                )
                db.commit()
                return digest
            except Exception:
                db.rollback()
                raise

    def verify(self) -> bool:
        with closing(self._connect()) as db:
            rows = db.execute(
                """SELECT event_id,schema_version,occurred_at,event_type,payload,
                previous_hash,event_hash FROM execution_observations ORDER BY seq"""
            ).fetchall()
        previous = "GENESIS"
        for event_id, version, occurred_at, event_type, payload, prev_hash, event_hash in rows:
            if prev_hash != previous:
                return False
            try:
                decoded = json.loads(payload)
                if (
                    decoded.get("schema_version") != version
                    or decoded.get("event_id") != event_id
                    or decoded.get("event_type") != event_type
                    or decoded.get("occurred_at") != occurred_at
                ):
                    return False
            except (TypeError, ValueError):
                return False
            expected = hashlib.sha256((previous + "|" + payload).encode("utf-8")).hexdigest()
            if expected != event_hash:
                return False
            previous = event_hash
        return True

    def has_event(self, event_id: str) -> bool:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT 1 FROM execution_observations WHERE event_id=?",
                (event_id,),
            ).fetchone()
        return row is not None

    def list_events(
        self, *, limit: int = 100, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit < 1 or limit > 10000:
            raise ValueError("limit must be between 1 and 10000")
        if not isinstance(after_seq, int) or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        with closing(self._connect()) as db:
            rows = db.execute(
                """SELECT seq,event_id,schema_version,occurred_at,event_type,payload,
                previous_hash,event_hash FROM execution_observations
                WHERE seq>? ORDER BY seq LIMIT ?""",
                (after_seq, limit),
            ).fetchall()
        return [{
            "seq": row[0], "event_id": row[1], "schema_version": row[2],
            "occurred_at": row[3], "event_type": row[4], "data": json.loads(row[5])["data"],
            "previous_hash": row[6], "event_hash": row[7],
        } for row in rows]
