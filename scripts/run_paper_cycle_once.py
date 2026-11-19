"""One-shot supervised research-cycle entrypoint.

Reads a signed observation produced by the independent Gate.io verifier, reads
operator controls from Supabase Postgres, commits at most one research decision,
prints a sanitized report, and exits. It cannot submit or authorize orders.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from research.gateio_attestation_verifier import VERIFIER_ID
from research.paper_cycle_orchestrator import run_once
from research.supabase_paper_state import SupabasePaperStateStore

MAX_OBSERVATION_BYTES = 256_000
DEFAULT_CONTROL_MAX_AGE_SECONDS = 180


def load_attested_observation(path: str) -> dict:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("attested observation must be a regular non-symlink file")
    if target.stat().st_size > MAX_OBSERVATION_BYTES:
        raise ValueError("attested observation exceeds size limit")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("attested observation must be a JSON object")
    attestation = value.get("trust_attestation")
    if not isinstance(attestation, dict) or attestation.get("verifier_id") != VERIFIER_ID:
        raise ValueError("observation was not signed by the configured independent verifier")
    if value.get("provenance_verified") is not False or value.get("evidence_credit") is not False:
        raise ValueError("verifier output must not self-award provenance or evidence credit")
    return value


def load_operator_controls(
    connection_factory: Callable,
    *,
    now: datetime | None = None,
    max_age_seconds: int = DEFAULT_CONTROL_MAX_AGE_SECONDS,
) -> dict | None:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("control-check clock must be timezone-aware")
    if max_age_seconds < 1:
        raise ValueError("control freshness threshold must be positive")
    with connection_factory() as db:
        with db.cursor() as cur:
            cur.execute(
                """select health, mode, kill_switch_engaged, entries_paused, reported_at
                   from public.operator_status
                   where worker_id = %s
                   order by reported_at desc
                   limit 1""",
                ("cloudflare-control-worker",),
            )
            row = cur.fetchone()
    if row is None:
        return None
    health, mode, kill_switch, entries_paused, reported_at = row
    if not isinstance(reported_at, datetime) or reported_at.tzinfo is None:
        return {
            "health": "stale_or_invalid",
            "mode": mode,
            "kill_switch_engaged": True,
            "entries_paused": True,
        }
    age = (current - reported_at.astimezone(timezone.utc)).total_seconds()
    if age < 0 or age > max_age_seconds:
        health = "stale_or_invalid"
        kill_switch = True
        entries_paused = True
    # Only strict boolean False permits a control to be considered disengaged.
    return {
        "health": health,
        "mode": mode,
        "kill_switch_engaged": kill_switch if isinstance(kill_switch, bool) else True,
        "entries_paused": entries_paused if isinstance(entries_paused, bool) else True,
    }


def main() -> int:
    try:
        dsn = os.environ["JARVIS_DATABASE_URL"]
        account_id = os.environ["JARVIS_PAPER_ACCOUNT_ID"]
        public_key = os.environ["JARVIS_GATEIO_VERIFIER_PUBLIC_KEY_B64"]
        observation_path = os.environ["JARVIS_ATTESTED_OBSERVATION_PATH"]
        import psycopg

        def connect():
            return psycopg.connect(
                dsn,
                connect_timeout=5,
                sslmode="require",
                options="-c statement_timeout=10000 -c lock_timeout=3000",
                application_name="jarvis-paper-cycle-runner",
            )

        observation = load_attested_observation(observation_path)
        controls = load_operator_controls(connect)
        store = SupabasePaperStateStore(dsn=dsn)
        result = run_once(
            store=store,
            account_id=account_id,
            observation=observation,
            controls=controls,
            trusted_verifier_public_key=public_key,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result.get("status") in {"blocked", "committed"} else 1
    except Exception as exc:
        # Error class only; never print DSNs, secrets, database bodies, or input payloads.
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "mode": "paper",
            "order_authorized": False,
            "orders_submitted": 0,
            "execution_started": False,
        }, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
