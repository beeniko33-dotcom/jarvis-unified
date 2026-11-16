"""Typed, append-only research lineage from observations through outcomes.

This ledger is a research record, not an execution interface. Hash chaining proves
local record integrity only; it does not authenticate providers or source origins.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ResearchStage(str, Enum):
    OBSERVATION = "observation"
    FEATURE = "feature"
    FORECAST = "forecast"
    DECISION = "decision"
    OUTCOME = "outcome"


_PARENT_STAGE = {
    ResearchStage.OBSERVATION: None,
    ResearchStage.FEATURE: ResearchStage.OBSERVATION,
    ResearchStage.FORECAST: ResearchStage.FEATURE,
    ResearchStage.DECISION: ResearchStage.FORECAST,
    ResearchStage.OUTCOME: ResearchStage.DECISION,
}
_FORBIDDEN_KEYS = (
    "password", "secret", "token", "api_key", "apikey", "private_key",
    "credential", "mnemonic", "wallet_seed",
)


def _utc(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _check_payload(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in _FORBIDDEN_KEYS):
                raise ValueError(f"secret-like field is not allowed at {path}.{key}")
            _check_payload(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_payload(item, f"{path}[{index}]")


@dataclass(frozen=True)
class ResearchEvent:
    event_id: str
    stage: ResearchStage
    occurred_at: datetime
    payload: dict[str, Any]
    parent_event_ids: tuple[str, ...] = ()
    source_ref: str = "not_recorded"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id is required")
        if not isinstance(self.stage, ResearchStage):
            raise ValueError("stage must be a ResearchStage")
        _utc(self.occurred_at, "occurred_at")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dictionary")
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ValueError("source_ref is required")
        if self.schema_version != 1:
            raise ValueError("unsupported research event schema version")
        if len(set(self.parent_event_ids)) != len(self.parent_event_ids):
            raise ValueError("parent_event_ids must be unique")
        if any(not isinstance(item, str) or not item.strip() for item in self.parent_event_ids):
            raise ValueError("parent event IDs must be non-empty strings")
        _check_payload(self.payload)
        json.dumps(self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class ResearchLineageError(ValueError):
    """A research event violates lineage, chronology, or idempotency rules."""


class ResearchEventLedger:
    """SQLite append-only event chain with strict stage lineage and chronology."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS research_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    schema_version INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    parent_ids_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS research_events_stage_idx ON research_events(stage, occurred_at)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    @staticmethod
    def _event_body(event: ResearchEvent) -> dict[str, Any]:
        return {
            "schema_version": event.schema_version,
            "event_id": event.event_id,
            "stage": event.stage.value,
            "occurred_at": _utc(event.occurred_at, "occurred_at"),
            "source_ref": event.source_ref,
            "parent_event_ids": list(event.parent_event_ids),
            "payload": event.payload,
        }

    def append(self, event: ResearchEvent) -> str:
        if not isinstance(event, ResearchEvent):
            raise TypeError("event must be a ResearchEvent")
        body = self._event_body(event)
        payload = self._canonical(body)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    """SELECT schema_version, stage, occurred_at, source_ref,
                              parent_ids_json, payload_json, event_hash
                       FROM research_events WHERE event_id=?""",
                    (event.event_id,),
                ).fetchone()
                if existing:
                    stored_body = {
                        "schema_version": existing[0],
                        "event_id": event.event_id,
                        "stage": existing[1],
                        "occurred_at": existing[2],
                        "source_ref": existing[3],
                        "parent_event_ids": json.loads(existing[4]),
                        "payload": json.loads(existing[5]),
                    }
                    if self._canonical(stored_body) != payload:
                        raise ResearchLineageError("event_id already exists with different content")
                    db.commit()
                    return existing[6]

                expected_parent = _PARENT_STAGE[event.stage]
                if expected_parent is None:
                    if event.parent_event_ids:
                        raise ResearchLineageError("observation events cannot have parent events")
                elif len(event.parent_event_ids) != 1:
                    raise ResearchLineageError(f"{event.stage.value} events require exactly one parent")
                else:
                    parent = db.execute(
                        "SELECT stage, occurred_at FROM research_events WHERE event_id=?",
                        (event.parent_event_ids[0],),
                    ).fetchone()
                    if parent is None:
                        raise ResearchLineageError("parent event does not exist")
                    if parent[0] != expected_parent.value:
                        raise ResearchLineageError(
                            f"{event.stage.value} requires a {expected_parent.value} parent"
                        )
                    if _utc(event.occurred_at, "occurred_at") < parent[1]:
                        raise ResearchLineageError("event chronology cannot precede its parent")

                tail = db.execute(
                    "SELECT event_hash FROM research_events ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                previous = tail[0] if tail else "GENESIS"
                digest = hashlib.sha256((previous + "|" + payload).encode("utf-8")).hexdigest()
                db.execute("""
                    INSERT INTO research_events
                    (event_id, schema_version, stage, occurred_at, source_ref,
                     parent_ids_json, payload_json, previous_hash, event_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id, event.schema_version, event.stage.value,
                    body["occurred_at"], event.source_ref,
                    self._canonical(body["parent_event_ids"]),
                    self._canonical(event.payload), previous, digest,
                ))
                db.commit()
                return digest
            except Exception:
                db.rollback()
                raise

    def verify(self) -> bool:
        with closing(self._connect()) as db:
            rows = db.execute("""
                SELECT event_id, schema_version, stage, occurred_at, source_ref,
                       parent_ids_json, payload_json, previous_hash, event_hash
                FROM research_events ORDER BY seq
            """).fetchall()
        previous = "GENESIS"
        known: dict[str, tuple[str, str]] = {}
        for row in rows:
            event_id, version, stage, occurred_at, source_ref, parents_json, payload_json, prev_hash, event_hash = row
            if prev_hash != previous:
                return False
            try:
                parents = json.loads(parents_json)
                payload = json.loads(payload_json)
                body = {
                    "schema_version": version, "event_id": event_id, "stage": stage,
                    "occurred_at": occurred_at, "source_ref": source_ref,
                    "parent_event_ids": parents, "payload": payload,
                }
                if self._canonical(body) == "":
                    return False
                expected = hashlib.sha256((previous + "|" + self._canonical(body)).encode("utf-8")).hexdigest()
                if expected != event_hash:
                    return False
                expected_parent = _PARENT_STAGE[ResearchStage(stage)]
                if expected_parent is None:
                    if parents:
                        return False
                else:
                    if len(parents) != 1 or parents[0] not in known:
                        return False
                    parent_stage, parent_time = known[parents[0]]
                    if parent_stage != expected_parent.value or occurred_at < parent_time:
                        return False
            except (KeyError, TypeError, ValueError):
                return False
            known[event_id] = (stage, occurred_at)
            previous = event_hash
        return True

    def report(self) -> dict[str, Any]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT stage, COUNT(*) FROM research_events GROUP BY stage"
            ).fetchall()
            total = db.execute("SELECT COUNT(*) FROM research_events").fetchone()[0]
        counts = {stage.value: 0 for stage in ResearchStage}
        counts.update({stage: count for stage, count in rows})
        return {
            "events": total,
            "by_stage": counts,
            "hash_chain_integrity": self.verify(),
            "provider_authenticity_verified": 0,
            "evidence_eligible": False,
            "status": "RESEARCH_ONLY",
        }
