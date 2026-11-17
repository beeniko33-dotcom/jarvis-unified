"""Local control worker: executes allowlisted, paper-only operator commands.

Runs on the operator's own machine with the Supabase service-role key from the environment.
It claims pending commands from ``public.operator_commands``, executes only the fixed actions
below, records a scrubbed result, and publishes a health snapshot to ``public.operator_status``.

Safety properties (each is tested):
- Fail closed: with no state file, entries are paused and the kill switch is treated as engaged.
- Fixed action table: any other action is rejected. Live trading is not a command.
- No operator-supplied text reaches a subprocess; the paper session command line is constant.
- Claims are atomic: a command already claimed by another worker is skipped.
- Results and heartbeats are built from allowlisted fields only, never raw exception text.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
MAX_RESULT_TEXT = 200
_SECRET_LIKE = re.compile(
    r"(key|token|secret|password|authorization|bearer|dsn|credential)\S*\s*[=:]\s*\S+",
    re.IGNORECASE,
)
_DEFAULT_STATE: dict[str, Any] = {
    "entries_paused": True,
    "kill_switch_engaged": True,
    "last_paper_session_date": None,
    "updated_at": None,
    "last_command_id": None,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _scrub(text: str) -> str:
    cleaned = _SECRET_LIKE.sub("[redacted]", str(text))
    return cleaned[:MAX_RESULT_TEXT]


# ---------------------------------------------------------------- local state (fail-closed)

class ControlState:
    """Single JSON file, written atomically. Missing or unreadable state means fully stopped."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(_DEFAULT_STATE)
        if not isinstance(data, dict):
            return dict(_DEFAULT_STATE)
        merged = dict(_DEFAULT_STATE)
        merged.update({k: data[k] for k in _DEFAULT_STATE if k in data})
        if not isinstance(merged["entries_paused"], bool) or not isinstance(merged["kill_switch_engaged"], bool):
            return dict(_DEFAULT_STATE)
        return merged

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)


# ---------------------------------------------------------------- Supabase REST (service role)

class SupabaseRest:
    def __init__(self, base_url: str, service_key: str, timeout: float = 15.0) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("SUPABASE_URL must use https")
        self.base = base_url.rstrip("/") + "/rest/v1"
        self._key = service_key
        self._timeout = timeout

    def _call(self, method: str, path: str, body: Any = None, prefer: str | None = None) -> Any:
        headers = {
            "apikey": self._key,
            "authorization": f"Bearer {self._key}",
            "content-type": "application/json",
        }
        if prefer:
            headers["prefer"] = prefer
        data = None if body is None else json.dumps(body).encode()
        req = urlrequest.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=self._timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            raise RuntimeError(f"supabase request failed with HTTP {exc.code}") from None
        except URLError:
            raise RuntimeError("supabase unreachable") from None

    def list_pending(self, limit: int = 10) -> list[dict]:
        return self._call(
            "GET",
            f"/operator_commands?status=eq.pending&order=requested_at.asc&limit={int(limit)}"
            "&select=id,action,idempotency_key,requested_at,reason",
        ) or []

    def claim(self, command_id: str, worker_id: str) -> bool:
        rows = self._call(
            "PATCH",
            f"/operator_commands?id=eq.{command_id}&status=eq.pending",
            {"status": "claimed", "claimed_by": worker_id, "claimed_at": _utc_now().isoformat()},
            prefer="return=representation",
        )
        return bool(rows)

    def finish(self, command_id: str, status: str, result: dict) -> None:
        self._call(
            "PATCH",
            f"/operator_commands?id=eq.{command_id}",
            {"status": status, "completed_at": _utc_now().isoformat(), "result": result},
            prefer="return=minimal",
        )

    def heartbeat(self, row: dict) -> None:
        self._call(
            "POST",
            "/operator_status?on_conflict=worker_id",
            row,
            prefer="resolution=merge-duplicates,return=minimal",
        )


# ---------------------------------------------------------------- fixed action handlers

PaperRunner = Callable[[list[str]], int]


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv, cwd=ROOT, timeout=900, check=False).returncode


@dataclass(frozen=True)
class Outcome:
    status: str  # completed | rejected | failed
    result: dict


def _set_flags(state: ControlState, **changes: Any) -> dict:
    current = state.load()
    current.update(changes)
    current["updated_at"] = _utc_now().isoformat()
    return current


def handle_pause(state: ControlState, command_id: str, _runner: PaperRunner, _cfg: dict) -> Outcome:
    updated = _set_flags(state, entries_paused=True, last_command_id=command_id)
    state.save(updated)
    return Outcome("completed", {"entries_paused": True, "kill_switch_engaged": updated["kill_switch_engaged"]})


def handle_resume(state: ControlState, command_id: str, _runner: PaperRunner, _cfg: dict) -> Outcome:
    current = state.load()
    if current["kill_switch_engaged"]:
        return Outcome("rejected", {"reason": "kill switch is engaged; resume refused"})
    updated = _set_flags(state, entries_paused=False, last_command_id=command_id)
    state.save(updated)
    return Outcome("completed", {"entries_paused": False, "kill_switch_engaged": False})


def handle_engage_kill(state: ControlState, command_id: str, _runner: PaperRunner, _cfg: dict) -> Outcome:
    updated = _set_flags(state, entries_paused=True, kill_switch_engaged=True, last_command_id=command_id)
    state.save(updated)
    return Outcome("completed", {"entries_paused": True, "kill_switch_engaged": True})


def handle_paper_session(state: ControlState, command_id: str, runner: PaperRunner, cfg: dict) -> Outcome:
    current = state.load()
    if current["kill_switch_engaged"] or current["entries_paused"]:
        return Outcome("rejected", {"reason": "entries are paused or the kill switch is engaged"})
    today = _utc_now().date().isoformat()
    if current["last_paper_session_date"] == today:
        return Outcome("rejected", {"reason": "a paper session already ran for this UTC day"})
    # Fixed argv: nothing from the command or the database reaches this list.
    argv = [
        sys.executable, str(ROOT / "scripts" / "paper_session.py"),
        "--allow-entries", "--account-db", str(cfg["account_db"]),
    ]
    code = runner(argv)
    if code != 0:
        return Outcome("failed", {"reason": "paper session exited with a non-zero status", "exit_code": code})
    updated = _set_flags(state, last_paper_session_date=today, last_command_id=command_id)
    state.save(updated)
    return Outcome("completed", {"paper_session_date": today})


ACTION_HANDLERS: dict[str, Callable[[ControlState, str, PaperRunner, dict], Outcome]] = {
    "pause_entries": handle_pause,
    "resume_entries": handle_resume,
    "engage_kill_switch": handle_engage_kill,
    "run_paper_session": handle_paper_session,
}


# ---------------------------------------------------------------- worker loop

def process_pending(
    rest: SupabaseRest,
    state: ControlState,
    *,
    worker_id: str,
    runner: PaperRunner = _default_runner,
    cfg: dict | None = None,
) -> list[dict]:
    cfg = cfg or {}
    handled: list[dict] = []
    for command in rest.list_pending():
        action = command.get("action")
        command_id = command.get("id")
        if not isinstance(command_id, str) or not isinstance(action, str):
            continue
        handler = ACTION_HANDLERS.get(action)
        if handler is None:
            # Never claim what we cannot execute: leave it visible for the operator.
            handled.append({"id": command_id, "action": action, "status": "skipped_unknown_action"})
            continue
        if not rest.claim(command_id, worker_id):
            handled.append({"id": command_id, "action": action, "status": "skipped_already_claimed"})
            continue
        try:
            outcome = handler(state, command_id, runner, cfg)
        except Exception as exc:  # noqa: BLE001 - reported as a scrubbed failure, never raised
            outcome = Outcome("failed", {"reason": _scrub(type(exc).__name__)})
        rest.finish(command_id, outcome.status, outcome.result)
        handled.append({"id": command_id, "action": action, "status": outcome.status})

    current = state.load()
    rest.heartbeat({
        "worker_id": worker_id,
        "reported_at": _utc_now().isoformat(),
        "health": "blocked" if current["kill_switch_engaged"] else (
            "degraded" if current["entries_paused"] else "healthy"
        ),
        "mode": "paper",
        "kill_switch_engaged": bool(current["kill_switch_engaged"]),
        "entries_paused": bool(current["entries_paused"]),
        "last_paper_session_date": current["last_paper_session_date"],
        "details": {"processed": len(handled)},
    })
    return handled


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "var" / "control" / "state.json")
    parser.add_argument("--account-db", type=Path, default=ROOT / "var" / "paper_account.sqlite3")
    parser.add_argument("--worker-id", default=os.environ.get("JARVIS_WORKER_ID", "local-control-worker"))
    parser.add_argument("--once", action="store_true", help="process pending commands once and exit")
    parser.add_argument("--interval", type=int, default=15, help="seconds between polls")
    parser.add_argument(
        "--release-kill-switch",
        action="store_true",
        help="LOCAL ONLY: clear the kill switch. Remote commands can never do this; run it by hand "
        "on the worker machine after review. Entries stay paused until resume_entries.",
    )
    args = parser.parse_args(argv)

    if args.release_kill_switch:
        state_file = ControlState(args.state)
        state_file.save(_set_flags(state_file, kill_switch_engaged=False, entries_paused=True))
        print(json.dumps({"kill_switch_engaged": False, "entries_paused": True,
                          "note": "entries remain paused; send resume_entries to allow paper entries"}))
        return 0

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in this shell's environment.")
        return 2
    rest = SupabaseRest(url, key)
    state = ControlState(args.state)
    cfg = {"account_db": args.account_db}

    import time

    while True:
        try:
            handled = process_pending(rest, state, worker_id=args.worker_id, cfg=cfg)
            print(json.dumps({"at": _utc_now().isoformat(), "handled": handled}))
        except RuntimeError as exc:
            print(json.dumps({"at": _utc_now().isoformat(), "error": _scrub(str(exc))}))
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
