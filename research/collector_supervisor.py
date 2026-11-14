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
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("jarvis.collector_supervisor")


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    started_at: str
    ended_at: str | None
    exit_code: int | None
    duration_seconds: int
    command: list[str]
    db_path: str
    status: str  # "running" | "completed" | "failed" | "skipped_lock"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"


class FileLock:
    """Simple exclusive lock using O_CREAT|O_EXCL.  Cross-process safe on local FS."""

    def __init__(self, path: Path, timeout_seconds: float = 5.0):
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._fd: int | None = None

    def acquire(self) -> bool:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self._fd, f"{os.getpid()}\n".encode())
                return True
            except FileExistsError:
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


def run_one_session(
    *,
    command: Sequence[str],
    db_path: Path,
    lock_path: Path,
    duration_seconds: int,
    log_dir: Path,
) -> SessionRecord:
    """Run a single collector command under exclusive lock."""
    sid = _session_id()
    started = _utc_now_iso()
    log_dir.mkdir(parents=True, exist_ok=True)
    session_log = log_dir / f"session-{sid}.json"

    lock = FileLock(lock_path, timeout_seconds=10.0)
    if not lock.acquire():
        record = SessionRecord(
            session_id=sid,
            started_at=started,
            ended_at=_utc_now_iso(),
            exit_code=None,
            duration_seconds=duration_seconds,
            command=list(command),
            db_path=str(db_path),
            status="skipped_lock",
        )
        session_log.write_text(json.dumps(asdict(record), indent=2))
        logger.warning("skipped session %s — lock held", sid)
        return record

    try:
        logger.info("starting session %s: %s", sid, " ".join(command))
        proc = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=duration_seconds + 60,  # hard ceiling
        )
        ended = _utc_now_iso()
        status = "completed" if proc.returncode == 0 else "failed"
        record = SessionRecord(
            session_id=sid,
            started_at=started,
            ended_at=ended,
            exit_code=proc.returncode,
            duration_seconds=duration_seconds,
            command=list(command),
            db_path=str(db_path),
            status=status,
        )
        # Persist stdout/stderr for operator review
        (log_dir / f"session-{sid}.stdout").write_text(proc.stdout or "")
        (log_dir / f"session-{sid}.stderr").write_text(proc.stderr or "")
        session_log.write_text(json.dumps(asdict(record), indent=2))
        logger.info("session %s finished status=%s exit=%s", sid, status, proc.returncode)
        return record
    except subprocess.TimeoutExpired:
        ended = _utc_now_iso()
        record = SessionRecord(
            session_id=sid,
            started_at=started,
            ended_at=ended,
            exit_code=-1,
            duration_seconds=duration_seconds,
            command=list(command),
            db_path=str(db_path),
            status="failed",
        )
        session_log.write_text(json.dumps(asdict(record), indent=2))
        logger.error("session %s timed out", sid)
        return record
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
) -> list[SessionRecord]:
    """Run successive non-overlapping sessions until max_sessions or interrupted."""
    results: list[SessionRecord] = []
    count = 0
    while max_sessions is None or count < max_sessions:
        record = run_one_session(
            command=command,
            db_path=db_path,
            lock_path=lock_path,
            duration_seconds=duration_seconds,
            log_dir=log_dir,
        )
        results.append(record)
        count += 1
        if max_sessions is not None and count >= max_sessions:
            break
        time.sleep(pause_between_seconds)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Jarvis collector session supervisor (paper / candidate data only)"
    )
    parser.add_argument(
        "--command",
        nargs="+",
        required=True,
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
        help="Seconds to wait between sessions",
    )
    parser.add_argument("--once", action="store_true", help="Run a single session and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    lock_path = args.lock or Path(str(args.db) + ".lock")
    args.log_dir.mkdir(parents=True, exist_ok=True)

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

    results = run_continuous(
        command=args.command,
        db_path=args.db,
        lock_path=lock_path,
        duration_seconds=args.duration_seconds,
        log_dir=args.log_dir,
        max_sessions=args.max_sessions,
        pause_between_seconds=args.pause_between,
    )
    print(json.dumps([asdict(r) for r in results], indent=2))
    return 0 if all(r.status == "completed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
