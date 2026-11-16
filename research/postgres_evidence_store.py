"""Optional Supabase/Postgres adapter for the market evidence pipeline.

SQLite remains the default and authoritative store until an explicit, reconciled
cutover. This adapter is opt-in, paper/research-only, and never submits orders.
"""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Callable

from research.evidence_pipeline import IngestResult, MarketObservation


class PostgresEvidenceStore:
    """Postgres implementation of the evidence-pipeline ingest/report contract.

    Pass a DB-API connection factory in tests. Production use lazily imports
    psycopg 3 and reads the DSN from JARVIS_DATABASE_URL.
    """

    def __init__(
        self,
        dsn: str | None = None,
        *,
        connection_factory: Callable[[], Any] | None = None,
        max_age_seconds: int = 120,
        max_future_skew_seconds: int = 5,
    ) -> None:
        import os

        if max_age_seconds < 0 or max_future_skew_seconds < 0:
            raise ValueError("time tolerances must be non-negative")
        self.dsn = dsn or os.environ.get("JARVIS_DATABASE_URL")
        self.connection_factory = connection_factory
        self.max_age_seconds = max_age_seconds
        self.max_future_skew_seconds = max_future_skew_seconds
        if not self.dsn and connection_factory is None:
            raise ValueError("JARVIS_DATABASE_URL is required for Postgres storage")

    def _connect(self):
        if self.connection_factory is not None:
            return self.connection_factory()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Postgres support requires the optional 'postgres' dependencies"
            ) from exc
        return psycopg.connect(
            self.dsn, connect_timeout=5, sslmode="require",
            application_name="jarvis-unified",
        )

    def ingest(
        self, observation: MarketObservation, *, now: datetime | None = None
    ) -> IngestResult:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        event_time = observation.event_time.astimezone(timezone.utc)
        received_at = observation.received_at.astimezone(timezone.utc)
        now = now.astimezone(timezone.utc)
        age = (now - event_time).total_seconds()
        stale = age > self.max_age_seconds
        clock_skew = (
            age < -self.max_future_skew_seconds
            or (received_at - now).total_seconds() > self.max_future_skew_seconds
        )
        values_json = json.dumps(
            observation.values, sort_keys=True, separators=(",", ":"), allow_nan=False
        )

        # Serialize ordering checks for the same source/instrument/interval.
        # The transaction-scoped lock is released automatically on commit/rollback.
        lock_key = "\x1f".join(
            (observation.source_id, observation.symbol, observation.timeframe)
        )
        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (lock_key,),
                    )
                    cursor.execute(
                        """
                        SELECT MAX(event_time)
                        FROM jarvis_private.market_observations
                        WHERE source_id = %s AND symbol = %s AND timeframe = %s
                        """,
                        (observation.source_id, observation.symbol, observation.timeframe),
                    )
                    previous = cursor.fetchone()[0]
                    out_of_order = (
                        previous is not None
                        and event_time < previous
                    )
                    cursor.execute(
                        """
                        INSERT INTO jarvis_private.market_observations (
                            source_id, event_time, received_at, symbol, timeframe,
                            schema_version, content_hash, values_json,
                            out_of_order, stale, clock_skew, provenance
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                            %s, %s, %s, 'candidate_unverified'
                        )
                        ON CONFLICT (source_id, content_hash) DO NOTHING
                        RETURNING out_of_order
                        """,
                        (
                            observation.source_id, event_time, received_at,
                            observation.symbol, observation.timeframe,
                            observation.schema_version, observation.content_hash,
                            values_json, out_of_order, stale, clock_skew,
                        ),
                    )
                    inserted = cursor.fetchone()
        if inserted is None:
            return IngestResult(
                False, True, False, stale, clock_skew, observation.content_hash
            )
        return IngestResult(
            True, False, bool(inserted[0]), stale, clock_skew,
            observation.content_hash,
        )

    def report(self, *, source_id: str | None = None) -> dict[str, Any]:
        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*), COALESCE(SUM(out_of_order::int), 0),
                               COALESCE(SUM(stale::int), 0),
                               COALESCE(SUM(clock_skew::int), 0),
                               COUNT(DISTINCT content_hash)
                        FROM jarvis_private.market_observations
                        WHERE (%s IS NULL OR source_id = %s)
                        """,
                        (source_id, source_id),
                    )
                    count, out_of_order, stale, skew, unique = cursor.fetchone()
                    cursor.execute(
                        """
                        SELECT DISTINCT source_id
                        FROM jarvis_private.market_observations
                        WHERE (%s IS NULL OR source_id = %s)
                        ORDER BY source_id
                        """,
                        (source_id, source_id),
                    )
                    sources = [row[0] for row in cursor.fetchall()]
        return {
            "observations": count,
            "unique_observations": unique,
            "out_of_order": out_of_order,
            "stale": stale,
            "clock_skew": skew,
            "sources": sources,
            "provenance": "candidate_unverified",
            "verified_observations": 0,
            "evidence_eligible": False,
            "status": "INSUFFICIENT_EVIDENCE",
        }

    def diagnostic(self) -> dict[str, Any]:
        """Read-only schema/connectivity diagnostic; never returns connection details."""
        with closing(self._connect()) as db:
            with db:
                with db.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(
                        """
                        SELECT current_setting('server_version'),
                               current_user,
                               to_regclass('jarvis_private.market_observations') IS NOT NULL,
                               to_regclass('jarvis_private.runtime_audit_events') IS NOT NULL,
                               to_regclass('jarvis_private.worker_heartbeats') IS NOT NULL
                        """
                    )
                    version, role, observations, audit, heartbeats = cursor.fetchone()
                    cursor.execute(
                        """
                        SELECT count(*)
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'jarvis_private'
                          AND c.relkind = 'r'
                          AND c.relrowsecurity
                        """
                    )
                    rls_tables = cursor.fetchone()[0]
        checks = {
            "market_observations_table": bool(observations),
            "runtime_audit_events_table": bool(audit),
            "worker_heartbeats_table": bool(heartbeats),
            "rls_enabled_on_three_tables": rls_tables == 3,
        }
        return {
            "status": "healthy" if all(checks.values()) else "degraded",
            "postgres_version": version,
            "database_role": role,
            "checks": checks,
            "rls_enabled_tables": rls_tables,
            "writes_performed": False,
            "trading_mode": "paper_only",
        }
