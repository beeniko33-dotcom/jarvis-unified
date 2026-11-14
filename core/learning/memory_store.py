"""Durable, local-first personal learning memory.

This store contains user preferences and learning candidates only. It is deliberately
separate from trading risk, execution, provenance and audit-ledger databases.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from core.sqlite_wal import enable_wal

_ALLOWED_SOURCES = {"explicit_user_feedback", "repeated_choice", "inferred_candidate"}
_SOURCE_PRIORITY = {
    "inferred_candidate": 1,
    "repeated_choice": 2,
    "explicit_user_feedback": 3,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_timestamp(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 string or None")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class LearningMemory:
    memory_id: str
    category: str
    memory_key: str
    content: str
    source: str
    confidence: float
    created_at: str
    updated_at: str
    review_after: str | None
    expires_at: str | None


class MemoryStore:
    """SQLite-backed personal preferences and tentative learning memories."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with closing(self._connect()) as db:
            enable_wal(db)
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS learning_memories (
                    memory_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL CHECK(source IN
                        ('explicit_user_feedback','repeated_choice','inferred_candidate')),
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    review_after TEXT,
                    expires_at TEXT,
                    UNIQUE(category, memory_key)
                );
                CREATE TABLE IF NOT EXISTS learning_memory_events (
                    event_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('created','updated','deleted')),
                    source TEXT,
                    occurred_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_learning_memory_category
                    ON learning_memories(category);
                CREATE INDEX IF NOT EXISTS idx_learning_memory_review
                    ON learning_memories(review_after);
                """
            )
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    @staticmethod
    def _validate_text(value: str, field: str, *, limit: int = 2000) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        value = value.strip()
        if len(value) > limit:
            raise ValueError(f"{field} exceeds {limit} characters")
        return value

    @staticmethod
    def _from_row(row: sqlite3.Row) -> LearningMemory:
        return LearningMemory(**dict(row))

    def put(
        self,
        category: str,
        memory_key: str,
        content: str,
        *,
        source: str = "explicit_user_feedback",
        confidence: float | None = None,
        review_after: str | None = None,
        expires_at: str | None = None,
    ) -> LearningMemory:
        """Create or update a memory; stronger provenance cannot be overwritten by weaker input."""
        category = self._validate_text(category, "category", limit=80).lower()
        memory_key = self._validate_text(memory_key, "memory_key", limit=120).lower()
        content = self._validate_text(content, "content")
        if source not in _ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {sorted(_ALLOWED_SOURCES)}")
        if confidence is None:
            confidence = 1.0 if source == "explicit_user_feedback" else (
                0.7 if source == "repeated_choice" else 0.4
            )
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be a number between 0 and 1")
        if not 0 <= float(confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if source == "explicit_user_feedback" and float(confidence) != 1.0:
            raise ValueError("explicit user feedback must have confidence 1.0")
        review_after = _validate_timestamp(review_after, "review_after")
        expires_at = _validate_timestamp(expires_at, "expires_at")
        now = _utc_now()

        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                prior = db.execute(
                    "SELECT * FROM learning_memories WHERE category=? AND memory_key=?",
                    (category, memory_key),
                ).fetchone()
                if prior and _SOURCE_PRIORITY[prior["source"]] > _SOURCE_PRIORITY[source]:
                    db.commit()
                    return self._from_row(prior)

                memory_id = prior["memory_id"] if prior else str(uuid.uuid4())
                created_at = prior["created_at"] if prior else now
                action = "updated" if prior else "created"
                db.execute(
                    """
                    INSERT INTO learning_memories
                    (memory_id,category,memory_key,content,source,confidence,created_at,
                     updated_at,review_after,expires_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(category,memory_key) DO UPDATE SET
                        content=excluded.content, source=excluded.source,
                        confidence=excluded.confidence, updated_at=excluded.updated_at,
                        review_after=excluded.review_after, expires_at=excluded.expires_at
                    """,
                    (memory_id, category, memory_key, content, source, float(confidence),
                     created_at, now, review_after, expires_at),
                )
                db.execute(
                    """INSERT INTO learning_memory_events
                    (event_id,memory_id,action,source,occurred_at,metadata_json)
                    VALUES(?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), memory_id, action, source, now,
                     json.dumps({"category": category, "key": memory_key})),
                )
                row = db.execute(
                    "SELECT * FROM learning_memories WHERE memory_id=?", (memory_id,)
                ).fetchone()
                db.commit()
                return self._from_row(row)
            except Exception:
                db.rollback()
                raise

    def get(self, category: str, memory_key: str) -> LearningMemory | None:
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM learning_memories WHERE category=? AND memory_key=?",
                (category.strip().lower(), memory_key.strip().lower()),
            ).fetchone()
        return self._from_row(row) if row else None

    def list_memories(
        self, *, category: str | None = None, include_expired: bool = False
    ) -> list[LearningMemory]:
        now = _utc_now()
        sql = "SELECT * FROM learning_memories"
        clauses: list[str] = []
        params: list[Any] = []
        if category is not None:
            clauses.append("category=?")
            params.append(category.strip().lower())
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY category,memory_key"
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(sql, params).fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, category: str, memory_key: str) -> bool:
        """Delete the memory content while retaining a content-free deletion event."""
        category = category.strip().lower()
        memory_key = memory_key.strip().lower()
        now = _utc_now()
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT memory_id,source FROM learning_memories WHERE category=? AND memory_key=?",
                    (category, memory_key),
                ).fetchone()
                if row is None:
                    db.commit()
                    return False
                db.execute(
                    "DELETE FROM learning_memories WHERE memory_id=?", (row["memory_id"],)
                )
                db.execute(
                    """INSERT INTO learning_memory_events
                    (event_id,memory_id,action,source,occurred_at,metadata_json)
                    VALUES(?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), row["memory_id"], "deleted", row["source"], now,
                     json.dumps({"category": category, "key": memory_key})),
                )
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise

    def export_json(self) -> str:
        """Export currently stored memories; deleted content is not included."""
        return json.dumps(
            [asdict(item) for item in self.list_memories(include_expired=True)],
            indent=2,
            sort_keys=True,
        )

    def event_history(self, *, memory_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT event_id,memory_id,action,source,occurred_at,metadata_json FROM learning_memory_events"
        params: tuple[str, ...] = ()
        if memory_id is not None:
            sql += " WHERE memory_id=?"
            params = (memory_id,)
        sql += " ORDER BY occurred_at,event_id"
        with self._lock, closing(self._connect()) as db:
            rows = db.execute(sql, params).fetchall()
        return [
            {**dict(row), "metadata": json.loads(row["metadata_json"])}
            for row in rows
        ]
