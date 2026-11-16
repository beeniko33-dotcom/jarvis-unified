"""Continuous session supervisor for duration-bounded market-data collectors.

Purpose
-------
The current Deriv / Biquote collectors are intentionally duration-bounded so a
single process cannot hold a SQLite writer open indefinitely.  For a persistent
host we still need a reliable way to run successive non-overlapping sessions,
record session boundaries, and resume after normal completion or crash.

This module provides that wrapper.  It does **not**:
- grant evidence credit
- open broker connections
- disable the kill switch
- change the BLOCKED_PROVENANCE gate

It only orchestrates successive collector runs under a file lock so two
writers never touch the same database concurrently.

Hardening (2026-11-14)
----------------------
- Stale-lock recovery: if the lock file exists but its recorded PID is not alive,
  the lock is treated as abandoned and removed.
- Consecutive-failure backoff: exponential pause after repeated failed sessions.
- Clean shutdown on SIGTERM / SIGINT: finishes the current session boundary
  write when possible, then exits the continuous loop.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("jarvis.collector_supervisor")

# Cooperative shutdown flag set by signal handlers.
_SHUTDOWN_REQUESTED = False


def _request_shutdown(signum: int, frame) -> None:  # noqa: ARG001
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    logger.info("shutdown requested via signal %s", signum)


def _install_signal_handlers() -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _request_shutdown)
        except (ValueError, OSError):
            # Not allowed in some threads / platforms; continuous mode still works.
            pass


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    started_at: str
    ended_at: str | None
    exit_code: int | None
    duration_seconds: int
    command: list[str]
    db_path: str
    status: str  # "completed" | "failed" | "skipped_lock" | "shutdown"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"-{os.getpid()}"


def _pid_is_alive(pid: int) -> bool:
    """Return True if *pid* appears to be a live process on this host."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we cannot signal it — treat as alive.
        return True
    except OSError:
        return False
    return True


def _read_lock_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text.splitlines()[0].strip())
    except (OSError, ValueError, IndexError):
        return None


class FileLock:
    """Exclusive lock using O_CREAT|O_EXCL, with stale-PID recovery.

    Cross-process safe on a local filesystem.  Not safe on NFS.
    """

    def __init__(self, path: Path, timeout_seconds: float = 5.0):
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._fd: int | None = None

    def _try_break_stale(self) -> bool:
        """If lock exists but owner PID is dead, remove it. Returns True if broken."""
        if not self.path.exists():
            return False
        pid = _read_lock_pid(self.path)
        if pid is None:
            # Unreadable / corrupt lock — leave it; operator intervention preferred
            # over blindly deleting an unknown lock.
            return False
        if _pid_is_alive(pid):
            return False
        try:
            self.path.unlink(missing_ok=True)
            logger.warning("removed stale lock %s (dead pid %s)", self.path, pid)
            return True
        except OSError as exc:
            logger.error("failed to remove stale lock %s: %s", self.path, exc)
            return False

    def acquire(self) -> bool:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                self._fd = os.open(
                    str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
                os.write(self._fd, f"{os.getpid()}\n".encode())
                return True
            except FileExistsError:
                # Attempt stale recovery once per spin iteration.
                self._try_break_stale()
                time.sleep(0.2)
        return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"could not acquire lock {self.path}")
        return self

    def __exit__(self, *exc):
        self.release()


def _terminate_and_reap(proc: subprocess.Popen, *, grace_seconds: float) -> int:
    """Stop the child (and its POSIX process group) and always reap the direct child."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except ProcessLookupError:
        pass
    except OSError:
        if proc.poll() is None:
            proc.terminate()
    try:
        return proc.wait(timeout=max(0.0, grace_seconds))
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        return proc.wait()


def run_one_session(
    *,
    command: Sequence[str],
    db_path: Path,
    lock_path: Path,
    duration_seconds: int,
    log_dir: Path,
    shutdown_grace_seconds: float = 5.0,
) -> SessionRecord:
    """Run one collector and promptly stop/reap it when shutdown is requested."""
    sid = _session_id()
    started = _utc_now_iso()
    started_monotonic = time.monotonic()
    log_dir.mkdir(parents=True, exist_ok=True)
    session_log = log_dir / f"session-{sid}.json"
    stdout_path = log_dir / f"session-{sid}.stdout"
    stderr_path = log_dir / f"session-{sid}.stderr"

    def write_record(record: SessionRecord) -> SessionRecord:
        session_log.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        return record

    lock = FileLock(lock_path, timeout_seconds=10.0)
    if not lock.acquire():
        record = SessionRecord(
            session_id=sid, started_at=started, ended_at=_utc_now_iso(),
            exit_code=None, duration_seconds=duration_seconds,
            command=[], db_path=str(db_path), status="skipped_lock",
        )
        logger.warning("skipped session %s — lock held", sid)
        return write_record(record)

    try:
        logger.info("starting session %s (executable=%s, argument_count=%s)", sid, Path(command[0]).name if command else "<none>", max(0, len(command) - 1))
        with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_file:
            proc = subprocess.Popen(
                list(command),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                start_new_session=(os.name == "posix"),
            )
            deadline = time.monotonic() + duration_seconds + 60
            status = "failed"
            exit_code: int | None = None
            while True:
                exit_code = proc.poll()
                if exit_code is not None:
                    status = "completed" if exit_code == 0 else "failed"
                    break
                if _SHUTDOWN_REQUESTED:
                    exit_code = _terminate_and_reap(
                        proc, grace_seconds=shutdown_grace_seconds
                    )
                    status = "shutdown"
                    break
                if time.monotonic() >= deadline:
                    _terminate_and_reap(proc, grace_seconds=shutdown_grace_seconds)
                    exit_code = -1
                    status = "failed"
                    logger.error("session %s timed out", sid)
                    break
                time.sleep(0.1)

        record = SessionRecord(
            session_id=sid, started_at=started, ended_at=_utc_now_iso(),
            exit_code=exit_code, duration_seconds=duration_seconds,
            command=[], db_path=str(db_path), status=status,
        )
        logger.info("session %s finished status=%s exit=%s", sid, status, exit_code)
        return write_record(record)
    except OSError as exc:
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        record = SessionRecord(
            session_id=sid, started_at=started, ended_at=_utc_now_iso(),
            exit_code=127, duration_seconds=duration_seconds,
            command=[], db_path=str(db_path), status="failed",
        )
        logger.exception("could not start session %s", sid)
        return write_record(record)
    finally:
        lock.release()


def run_continuous(
    *,
    command: Sequence[str],
    db_path: Path,
    lock_path: Path,
    duration_seconds: int,
    log_dir: Path,
    max_sessions: int | None = None,
    pause_between_seconds: float = 5.0,
    max_consecutive_failures: int = 5,
    backoff_base_seconds: float = 15.0,
    backoff_cap_seconds: float = 300.0,
    reporter=None,
) -> list[SessionRecord]:
    """Run successive non-overlapping sessions until max_sessions, failure budget, or shutdown.

    After each failed / skipped session the pause grows exponentially
    (backoff_base * 2^(n-1)), capped at backoff_cap_seconds.  A successful
    session resets the failure counter.
    """
    results: list[SessionRecord] = []
    count = 0
    consecutive_failures = 0

    if reporter is not None:
        reporter.emit_event("supervisor.started", health="healthy", details={"status": "running"})
    while max_sessions is None or count < max_sessions:
        if _SHUTDOWN_REQUESTED:
            logger.info("exiting continuous loop — shutdown requested")
            break

        if reporter is not None:
            reporter.emit_event("supervisor.session_started", health="healthy", details={"duration_seconds": duration_seconds})
        record = run_one_session(
            command=command,
            db_path=db_path,
            lock_path=lock_path,
            duration_seconds=duration_seconds,
            log_dir=log_dir,
        )
        results.append(record)
        count += 1
        if reporter is not None:
            event = "supervisor.session_completed" if record.status == "completed" else "supervisor.session_" + record.status
            health = "healthy" if record.status == "completed" else ("blocked" if record.status == "skipped_lock" else "degraded")
            reporter.emit_event(event, health=health, details={"status": record.status, "duration_seconds": record.duration_seconds, "exit_code": record.exit_code})

        if record.status == "completed":
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                logger.error(
                    "stopping after %s consecutive failures (limit %s)",
                    consecutive_failures,
                    max_consecutive_failures,
                )
                break

        if max_sessions is not None and count >= max_sessions:
            break

        if _SHUTDOWN_REQUESTED:
            break

        # Backoff only after non-success; otherwise use the configured pause.
        if record.status == "completed":
            pause = pause_between_seconds
        else:
            pause = min(
                backoff_base_seconds * (2 ** (consecutive_failures - 1)),
                backoff_cap_seconds,
            )
        logger.info("pausing %.1fs before next session", pause)
        if reporter is not None and record.status != "completed":
            reporter.emit_event("supervisor.backoff", health="degraded", details={"failure_count": consecutive_failures, "pause_seconds": pause, "status": record.status})
        # Interruptible sleep
        end = time.monotonic() + pause
        while time.monotonic() < end:
            if _SHUTDOWN_REQUESTED:
                break
            time.sleep(min(0.5, end - time.monotonic()))

    if reporter is not None:
        reporter.emit_event("supervisor.stopped", health="stopped", details={"status": "shutdown" if _SHUTDOWN_REQUESTED else "completed"})
    return results


def health_snapshot(
    *,
    log_dir: Path,
    db_path: Path,
    lock_path: Path,
) -> dict:
    """Lightweight operator health view (not market-data evidence)."""
    sessions = sorted(log_dir.glob("session-*.json")) if log_dir.exists() else []
    last = None
    if sessions:
        try:
            last = json.loads(sessions[-1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            last = {"error": "unreadable"}

    lock_pid = _read_lock_pid(lock_path) if lock_path.exists() else None
    return {
        "supervisor_pid": os.getpid(),
        "utc_now": _utc_now_iso(),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "lock_path": str(lock_path),
        "lock_held": lock_path.exists(),
        "lock_pid": lock_pid,
        "lock_pid_alive": _pid_is_alive(lock_pid) if lock_pid is not None else None,
        "session_record_count": len(sessions),
        "last_session": last,
        "shutdown_requested": _SHUTDOWN_REQUESTED,
        "note": "Operator metadata only. Not Level 3 evidence.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Jarvis collector session supervisor (paper / candidate data only)"
    )
    parser.add_argument(
        "--command",
        nargs="+",
        required=False,
        help="Collector command to run (e.g. python -m research.deriv_feed --duration-seconds 3600 ...)",
    )
    parser.add_argument("--db", type=Path, required=True, help="SQLite database path")
    parser.add_argument(
        "--lock", type=Path, default=None, help="Lock file path (default: <db>.lock)"
    )
    parser.add_argument(
        "--duration-seconds", type=int, default=3600, help="Expected session duration"
    )
    parser.add_argument(
        "--log-dir", type=Path, default=Path("var/collector_sessions"),
        help="Directory for session records and logs",
    )
    parser.add_argument(
        "--max-sessions", type=int, default=None,
        help="Stop after N sessions (default: run forever)",
    )
    parser.add_argument(
        "--pause-between", type=float, default=5.0,
        help="Seconds to wait between successful sessions",
    )
    parser.add_argument(
        "--max-consecutive-failures", type=int, default=5,
        help="Stop continuous mode after this many failures in a row",
    )
    parser.add_argument(
        "--backoff-base", type=float, default=15.0,
        help="Base seconds for exponential backoff after failures",
    )
    parser.add_argument(
        "--backoff-cap", type=float, default=300.0,
        help="Maximum backoff seconds",
    )
    parser.add_argument("--once", action="store_true", help="Run a single session and exit")
    parser.add_argument(
        "--health", action="store_true",
        help="Print a JSON health snapshot and exit (no collector started)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    lock_path = args.lock or Path(str(args.db) + ".lock")
    args.log_dir.mkdir(parents=True, exist_ok=True)

    if args.health:
        print(json.dumps(
            health_snapshot(log_dir=args.log_dir, db_path=args.db, lock_path=lock_path),
            indent=2,
        ))
        return 0

    if not args.command:
        parser.error("--command is required unless --health is used")

    _install_signal_handlers()

    if args.once:
        record = run_one_session(
            command=args.command,
            db_path=args.db,
            lock_path=lock_path,
            duration_seconds=args.duration_seconds,
            log_dir=args.log_dir,
        )
        print(json.dumps(asdict(record), indent=2))
        return 0 if record.status == "completed" else 1

    reporter = None
    try:
        from research.control_plane_runtime import ControlPlaneReporter
        reporter = ControlPlaneReporter.from_environment()
        if reporter is not None:
            reporter.worker_type = "collector_supervisor"
            reporter.component = "collector_supervisor"
            reporter.worker_id = f"jarvis-collector-supervisor-{os.getpid()}"[:128]
            reporter.start()
    except Exception as exc:  # noqa: BLE001 - telemetry must never block local collection
        logger.warning("control-plane reporter unavailable (%s)", type(exc).__name__)
        reporter = None

    try:
        results = run_continuous(
        command=args.command,
        db_path=args.db,
        lock_path=lock_path,
        duration_seconds=args.duration_seconds,
        log_dir=args.log_dir,
        max_sessions=args.max_sessions,
        pause_between_seconds=args.pause_between,
        max_consecutive_failures=args.max_consecutive_failures,
        backoff_base_seconds=args.backoff_base,
        backoff_cap_seconds=args.backoff_cap,
        reporter=reporter,
        )
    finally:
        if reporter is not None:
            reporter.stop()
    print(json.dumps([asdict(r) for r in results], indent=2))
    return 0 if results and all(r.status == "completed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
