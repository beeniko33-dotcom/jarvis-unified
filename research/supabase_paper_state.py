"""Transactional Supabase persistence for paper-account snapshots and cycle ledgers.

This adapter stores paper state only. It does not import broker interfaces, submit
orders, or change the local SQLite broker's default behavior. A cycle commit is
atomic: idempotency record, hash-chained events, and the new snapshot commit together.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_EVENT_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|authorization|api[_-]?key|private[_-]?key|"
    r"seed|mnemonic|wallet|credential|cookie|session|dsn|connection[_-]?string)",
    re.IGNORECASE,
)
_GENESIS = "GENESIS"


class PaperStateConflict(RuntimeError):
    """The stored account revision differs from the caller's expected revision."""


class PaperStateIntegrityError(RuntimeError):
    """Stored paper state or its hash chain failed verification."""


def _canonical(value: Any, *, max_bytes: int) -> tuple[str, str]:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"JSON payload exceeds {max_bytes} bytes")
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_json(value: Any, *, max_bytes: int = 1_000_000) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ValueError("paper state must be a JSON object")
    def walk(item: Any, depth: int = 0) -> None:
        if depth > 12:
            raise ValueError("paper state nesting exceeds 12 levels")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or not key or len(key) > 128:
                    raise ValueError("paper state keys must be non-empty strings up to 128 chars")
                if _SECRET_KEY.search(key):
                    raise ValueError("paper state contains a credential-like field")
                walk(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 10000:
                raise ValueError("paper state array exceeds 10000 items")
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 16384:
                raise ValueError("paper state string exceeds 16384 characters")
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise ValueError("paper state must contain JSON scalar values only")
    walk(value)
    return _canonical(value, max_bytes=max_bytes)


class SupabasePaperStateStore:
    """Atomic snapshot/ledger store backed by the private jarvis_private schema."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        connection_factory: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.dsn = dsn or os.environ.get("JARVIS_DATABASE_URL")
        self.connection_factory = connection_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if not self.dsn and connection_factory is None:
            raise ValueError("JARVIS_DATABASE_URL is required for Supabase paper-state storage")

    def _connect(self):
        if self.connection_factory is not None:
            return self.connection_factory()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install the pinned 'postgres' optional dependencies") from exc
        return psycopg.connect(
            self.dsn,
            connect_timeout=5,
            sslmode="require",
            options="-c statement_timeout=10000 -c lock_timeout=3000",
            application_name="jarvis-unified-paper-state",
        )

    @staticmethod
    def _account_id(value: str) -> str:
        if not isinstance(value, str) or not _ACCOUNT_ID.fullmatch(value):
            raise ValueError("account_id must be 1-128 safe identifier characters")
        return value

    def load_account(self, account_id: str) -> dict | None:
        account_id = self._account_id(account_id)
        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cur:
                    cur.execute(
                        """select revision, state::text, state_sha256, last_run_id::text, mode
                           from jarvis_private.paper_accounts where account_id = %s""",
                        (account_id,),
                    )
                    row = cur.fetchone()
        if row is None:
            return None
        revision, state_text, expected_hash, last_run_id, mode = row
        if mode != "paper":
            raise PaperStateIntegrityError("stored account mode is not paper")
        try:
            state = json.loads(state_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PaperStateIntegrityError("stored account state is invalid JSON") from exc
        _, actual_hash = _validate_json(state)
        if actual_hash != expected_hash:
            raise PaperStateIntegrityError("stored account state hash mismatch")
        return {
            "account_id": account_id,
            "mode": "paper",
            "revision": int(revision),
            "state": state,
            "state_sha256": actual_hash,
            "last_run_id": str(last_run_id),
        }

    def commit_cycle(
        self,
        *,
        account_id: str,
        run_id: str,
        expected_revision: int,
        state: dict,
        events: list[dict],
        input_fingerprint: dict,
        metadata: dict | None = None,
    ) -> dict:
        """Atomically commit one completed paper cycle, rejecting duplicates/stale writers."""
        account_id = self._account_id(account_id)
        try:
            run_uuid = str(UUID(run_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("run_id must be a UUID") from exc
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        state_json, state_hash = _validate_json(state)
        input_json, input_hash = _validate_json(input_fingerprint)
        metadata_json, _ = _validate_json(metadata or {})
        if not isinstance(events, list) or not events or len(events) > 1000:
            raise ValueError("each cycle must include 1-1000 ledger events")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        prepared = []
        for event in events:
            if not isinstance(event, dict) or not _EVENT_TYPE.fullmatch(str(event.get("event_type", ""))):
                raise ValueError("each ledger event needs a safe event_type")
            payload = event.get("payload", {})
            payload_json, _ = _validate_json(payload, max_bytes=16384)
            occurred_at = event.get("occurred_at", now)
            if isinstance(occurred_at, str):
                try:
                    occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError("event occurred_at must be ISO-8601") from exc
            if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
                raise ValueError("event occurred_at must be timezone-aware")
            prepared.append((event["event_type"], occurred_at.astimezone(timezone.utc), payload_json))

        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cur:
                    # Serialize account creation and all cycle commits, including the first.
                    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (account_id,))
                    cur.execute(
                        """select revision from jarvis_private.paper_accounts
                           where account_id = %s for update""",
                        (account_id,),
                    )
                    row = cur.fetchone()
                    current_revision = int(row[0]) if row else 0
                    cur.execute(
                        """select account_id, input_sha256, state_sha256, status
                           from jarvis_private.paper_runs where run_id = %s""",
                        (run_uuid,),
                    )
                    prior = cur.fetchone()
                    if prior:
                        if prior[0] != account_id or prior[1] != input_hash or prior[2] != state_hash or prior[3] != "completed":
                            raise PaperStateConflict("run_id already exists with different cycle content")
                        return {
                            "account_id": account_id, "run_id": run_uuid,
                            "revision": current_revision, "state_sha256": state_hash,
                            "duplicate": True, "mode": "paper",
                        }
                    if current_revision != expected_revision:
                        raise PaperStateConflict(
                            f"expected revision {expected_revision}, found {current_revision}"
                        )
                    cur.execute(
                        """select sequence, event_hash from jarvis_private.paper_ledger_events
                           where account_id = %s order by sequence desc limit 1 for update""",
                        (account_id,),
                    )
                    tail = cur.fetchone()
                    sequence = int(tail[0]) if tail else 0
                    previous_hash = tail[1] if tail else _GENESIS
                    # The run row references its account, so create a first snapshot
                    # inside this same transaction before inserting the run/ledger rows.
                    if row is None:
                        cur.execute(
                            """insert into jarvis_private.paper_accounts
                               (account_id, mode, revision, state, state_sha256, last_run_id, updated_at)
                               values (%s, 'paper', %s, %s::jsonb, %s, %s, %s)""",
                            (account_id, expected_revision + 1, state_json, state_hash, run_uuid, now),
                        )
                    cur.execute(
                        """insert into jarvis_private.paper_runs
                           (run_id, account_id, mode, status, revision_before, revision_after,
                            input_sha256, state_sha256, started_at, completed_at, metadata)
                           values (%s, %s, 'paper', 'completed', %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                        (run_uuid, account_id, expected_revision, expected_revision + 1,
                         input_hash, state_hash, now, now, metadata_json),
                    )
                    for event_type, occurred_at, payload_json in prepared:
                        sequence += 1
                        material = json.dumps(
                            {"account_id": account_id, "sequence": sequence,
                             "run_id": run_uuid, "event_type": event_type,
                             "occurred_at": occurred_at.isoformat(),
                             "payload": json.loads(payload_json)},
                            sort_keys=True, separators=(",", ":"), allow_nan=False,
                        )
                        digest = hashlib.sha256((previous_hash + "|" + material).encode()).hexdigest()
                        cur.execute(
                            """insert into jarvis_private.paper_ledger_events
                               (account_id, run_id, sequence, event_type, occurred_at,
                                payload, previous_hash, event_hash)
                               values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
                            (account_id, run_uuid, sequence, event_type, occurred_at,
                             payload_json, previous_hash, digest),
                        )
                        previous_hash = digest
                    if row is not None:
                        cur.execute(
                            """update jarvis_private.paper_accounts
                               set mode = 'paper', revision = %s, state = %s::jsonb,
                                   state_sha256 = %s, last_run_id = %s, updated_at = %s
                               where account_id = %s""",
                            (expected_revision + 1, state_json, state_hash, run_uuid, now, account_id),
                        )
        return {
            "account_id": account_id, "run_id": run_uuid,
            "revision": expected_revision + 1, "state_sha256": state_hash,
            "duplicate": False, "mode": "paper",
        }
