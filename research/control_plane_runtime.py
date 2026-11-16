"""Best-effort, opt-in lifecycle reporting for the paper-only status process.

Database outages must never prevent the local paper runtime from starting or
serving status. No broker or order interfaces are imported here.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import datetime, timezone
from typing import Any, Callable


_LOG = logging.getLogger(__name__)


class ControlPlaneReporter:
    """Emit periodic paper-mode heartbeats and lifecycle audit events."""

    def __init__(
        self,
        store: Any,
        *,
        worker_id: str | None = None,
        interval_seconds: float = 60.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.store = store
        self.worker_id = worker_id or f"jarvis-status-api-{socket.gethostname()}"[:128]
        self.interval_seconds = interval_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.started_at: datetime | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_environment(cls) -> "ControlPlaneReporter | None":
        enabled = os.getenv("JARVIS_SUPABASE_CONTROL_PLANE_ENABLED", "false").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return None
        try:
            from research.supabase_control_plane import SupabaseControlPlaneStore

            return cls(SupabaseControlPlaneStore())
        except Exception as exc:  # noqa: BLE001 - fail open; never print exception text
            _LOG.warning("Supabase control-plane reporting unavailable (%s); paper runtime continues",
                         type(exc).__name__)
            return None

    def _emit(self, health: str, event_type: str) -> None:
        now = self.clock()
        try:
            self.store.record_heartbeat(
                worker_id=self.worker_id,
                worker_type="status_api",
                reported_at=now,
                started_at=self.started_at,
                software_version="0.2.0",
                git_commit=os.getenv("GIT_COMMIT") or None,
                health=health,
                details={"component": "read_only_status_api", "mode": "paper"},
            )
        except Exception as exc:  # noqa: BLE001 - observability must not gate runtime
            _LOG.warning("Supabase heartbeat write failed (%s)", type(exc).__name__)
        try:
            self.store.append_audit_event(
                event_type=event_type,
                occurred_at=now,
                component="status_api",
                payload={"worker_id": self.worker_id, "mode": "paper", "health": health},
            )
        except Exception as exc:  # noqa: BLE001 - do not leak DSN/driver text
            _LOG.warning("Supabase lifecycle audit write failed (%s)", type(exc).__name__)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._emit("healthy", "worker.heartbeat")

    def start(self) -> None:
        if self._thread is not None:
            return
        self.started_at = self.clock()
        self._emit("healthy", "worker.started")
        self._thread = threading.Thread(
            target=self._run, name="jarvis-control-plane-heartbeat", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=min(self.interval_seconds, 2.0) + 1.0)
        self._emit("stopped", "worker.stopped")
        self._thread = None
