"""Opt-in Supabase control-plane writes for worker health and audit events.

This module is backend-only. It never handles broker execution and hard-enforces
paper mode. SQLite remains the application's default until a separately reviewed
migration and reconciliation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Callable

_SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|authorization|api[_-]?key|private[_-]?key|"
    r"seed|mnemonic|wallet|credential|cookie|session|dsn|connection[_-]?string)",
    re.IGNORECASE,
)
_HEALTH = {"healthy", "degraded", "stopped", "blocked"}
_MAX_PAYLOAD_BYTES = 16_384


def _timestamp(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _safe_payload(payload: dict[str, Any] | None) -> tuple[dict[str, Any], str, str]:
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    def inspect(value: Any, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("payload nesting exceeds limit")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or not key or len(key) > 128:
                    raise ValueError("payload keys must be non-empty strings of at most 128 characters")
                if _SECRET_KEY.search(key):
                    raise ValueError("payload contains a credential-like field")
                inspect(child, depth + 1)
        elif isinstance(value, list):
            if len(value) > 256:
                raise ValueError("payload array exceeds limit")
            for child in value:
                inspect(child, depth + 1)
        elif isinstance(value, str):
            if len(value) > 4096:
                raise ValueError("payload string exceeds limit")
        elif value is not None and not isinstance(value, (bool, int, float)):
            raise ValueError("payload must contain JSON scalar values only")

    inspect(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ValueError("payload exceeds 16 KiB")
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return payload, encoded, digest


class SupabaseControlPlaneStore:
    """Writes heartbeat snapshots and append-only audit records to jarvis_private."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.dsn = dsn or os.environ.get("JARVIS_DATABASE_URL")
        self.connection_factory = connection_factory
        if not self.dsn and connection_factory is None:
            raise ValueError("JARVIS_DATABASE_URL is required for Supabase control-plane storage")

    def _connect(self):
        if self.connection_factory is not None:
            return self.connection_factory()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Postgres support requires the optional 'postgres' dependencies") from exc
        return psycopg.connect(
            self.dsn, connect_timeout=5, sslmode="require",
            options="-c statement_timeout=5000 -c lock_timeout=2000",
            application_name="jarvis-unified-control-plane",
        )

    def record_heartbeat(
        self,
        *,
        worker_id: str,
        worker_type: str,
        reported_at: datetime,
        started_at: datetime | None,
        software_version: str,
        git_commit: str | None,
        health: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not worker_id.strip() or len(worker_id) > 128:
            raise ValueError("worker_id must contain 1 to 128 characters")
        if not worker_type.strip() or len(worker_type) > 64:
            raise ValueError("worker_type must contain 1 to 64 characters")
        if not software_version.strip() or len(software_version) > 128:
            raise ValueError("software_version must contain 1 to 128 characters")
        if git_commit is not None and len(git_commit) > 64:
            raise ValueError("git_commit must be at most 64 characters")
        if health not in _HEALTH:
            raise ValueError("health must be healthy, degraded, stopped, or blocked")
        reported = _timestamp(reported_at, "reported_at")
        started = _timestamp(started_at, "started_at") if started_at else None
        if started and started > reported:
            raise ValueError("started_at cannot be after reported_at")
        _, details_json, _ = _safe_payload(details)

        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO jarvis_private.worker_heartbeats (
                            worker_id, worker_type, reported_at, started_at,
                            software_version, git_commit, mode, health, details, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'paper', %s, %s::jsonb, now())
                        ON CONFLICT (worker_id) DO UPDATE SET
                            worker_type = EXCLUDED.worker_type,
                            reported_at = EXCLUDED.reported_at,
                            started_at = EXCLUDED.started_at,
                            software_version = EXCLUDED.software_version,
                            git_commit = EXCLUDED.git_commit,
                            mode = 'paper',
                            health = EXCLUDED.health,
                            details = EXCLUDED.details,
                            updated_at = now()
                        WHERE jarvis_private.worker_heartbeats.reported_at <= EXCLUDED.reported_at
                        """,
                        (
                            worker_id, worker_type, reported, started,
                            software_version, git_commit, health, details_json,
                        ),
                    )

    def append_audit_event(
        self,
        *,
        event_type: str,
        occurred_at: datetime,
        component: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> str:
        if not event_type.strip() or len(event_type) > 128:
            raise ValueError("event_type must contain 1 to 128 characters")
        if not component.strip() or len(component) > 128:
            raise ValueError("component must contain 1 to 128 characters")
        if correlation_id is not None and len(correlation_id) > 128:
            raise ValueError("correlation_id must be at most 128 characters")
        occurred = _timestamp(occurred_at, "occurred_at")
        _, payload_json, digest = _safe_payload(payload)

        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO jarvis_private.runtime_audit_events (
                            event_type, occurred_at, correlation_id, component,
                            payload, payload_sha256
                        ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                        RETURNING id::text
                        """,
                        (event_type, occurred, correlation_id, component, payload_json, digest),
                    )
                    row = cursor.fetchone()
        return row[0]
