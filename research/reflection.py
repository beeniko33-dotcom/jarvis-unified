"""Factual session reflections built only from explicitly supplied event records.

The builder never infers market outcomes or treats unverified data as authentic.
Patterns are framed as hypotheses, not facts, and are never applied automatically.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_ALLOWED_PROVENANCE = {"historical", "synthetic", "unverified_candidate", "verified", "not_applicable"}


def _utc(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("event timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("event timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class SessionEvent:
    event_id: str
    occurred_at: str
    event_type: str
    summary: str
    source_ref: str
    provenance: str = "not_applicable"
    owner_correction: bool = False


@dataclass(frozen=True)
class SessionReflection:
    reflection_id: str
    session_id: str
    created_at: str
    event_count: int
    facts: list[dict[str, Any]]
    owner_corrections: list[dict[str, Any]]
    hypotheses: list[str]
    unknowns: list[str]
    next_low_risk_steps: list[str]
    event_ids: list[str]


class ReflectionStore:
    """Persist factual reflection snapshots separately from execution/audit ledgers."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS session_reflections (
                    reflection_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_reflections_session ON session_reflections(session_id)")
            db.commit()

    def build(
        self, *, session_id: str, events: Iterable[SessionEvent],
        unknowns: list[str] | None = None, next_low_risk_steps: list[str] | None = None,
    ) -> SessionReflection:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id is required")
        normalized: list[SessionEvent] = []
        seen: set[str] = set()
        for event in events:
            if not isinstance(event, SessionEvent):
                raise ValueError("events must contain SessionEvent records")
            if not event.event_id or event.event_id in seen:
                raise ValueError("event IDs must be non-empty and unique")
            seen.add(event.event_id)
            if not event.event_type.strip() or not event.summary.strip() or not event.source_ref.strip():
                raise ValueError("event_type, summary and source_ref are required")
            if event.provenance not in _ALLOWED_PROVENANCE:
                raise ValueError("unknown provenance label")
            normalized.append(SessionEvent(
                event_id=event.event_id, occurred_at=_utc(event.occurred_at),
                event_type=event.event_type, summary=event.summary,
                source_ref=event.source_ref, provenance=event.provenance,
                owner_correction=bool(event.owner_correction),
            ))
        normalized.sort(key=lambda item: (item.occurred_at, item.event_id))
        facts = [
            {
                "event_id": item.event_id, "occurred_at": item.occurred_at,
                "event_type": item.event_type, "statement": item.summary,
                "source_ref": item.source_ref, "provenance": item.provenance,
            }
            for item in normalized
        ]
        corrections = [fact for fact, event in zip(facts, normalized) if event.owner_correction]
        hypotheses: list[str] = []
        if len(normalized) >= 2:
            by_type: dict[str, int] = {}
            for item in normalized:
                by_type[item.event_type] = by_type.get(item.event_type, 0) + 1
            repeated = sorted(kind for kind, count in by_type.items() if count >= 2)
            if repeated:
                hypotheses.append(
                    "Repeated event types were observed: " + ", ".join(repeated)
                    + ". This is a workflow pattern to review, not proof of improved performance."
                )
        reflection = SessionReflection(
            reflection_id=str(uuid.uuid4()), session_id=session_id.strip(),
            created_at=datetime.now(timezone.utc).isoformat(), event_count=len(facts),
            facts=facts, owner_corrections=corrections, hypotheses=hypotheses,
            unknowns=list(unknowns or ["No outcome or causal conclusion is available unless recorded in the source events."]),
            next_low_risk_steps=list(next_low_risk_steps or ["Review the cited events and decide whether any proposed workflow change is useful."]),
            event_ids=[item.event_id for item in normalized],
        )
        payload = json.dumps(asdict(reflection), sort_keys=True, allow_nan=False)
        with closing(sqlite3.connect(self.database_path)) as db:
            db.execute(
                "INSERT INTO session_reflections VALUES (?,?,?,?,?)",
                (reflection.reflection_id, reflection.session_id, reflection.created_at,
                 reflection.event_count, payload),
            )
            db.commit()
        return reflection

    def get(self, reflection_id: str) -> SessionReflection | None:
        with closing(sqlite3.connect(self.database_path)) as db:
            row = db.execute(
                "SELECT payload_json FROM session_reflections WHERE reflection_id=?",
                (reflection_id,),
            ).fetchone()
        return SessionReflection(**json.loads(row[0])) if row else None

    def list_for_session(self, session_id: str) -> list[SessionReflection]:
        with closing(sqlite3.connect(self.database_path)) as db:
            rows = db.execute(
                "SELECT payload_json FROM session_reflections WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [SessionReflection(**json.loads(row[0])) for row in rows]
