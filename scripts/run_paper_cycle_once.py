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
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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


def fetch_attested_observation(url: str) -> dict:
    parsed = urlparse(url)
    if (parsed.scheme != "https"
            or parsed.hostname != "jarvis-gateio-attestor.beeniko33.workers.dev"
            or parsed.path != "/v1/attestation"
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError("attested observation URL is not the pinned HTTPS verifier")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "JarvisPaperRunner/1.0"})
    with urlopen(request, timeout=15) as response:
        if response.status != 200 or urlparse(response.geturl()).hostname != parsed.hostname:
            raise ValueError("independent verifier did not return a valid response")
        raw = response.read(MAX_OBSERVATION_BYTES + 1)
    if len(raw) > MAX_OBSERVATION_BYTES:
        raise ValueError("attested observation exceeds size limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("attested observation must be a JSON object")
    attestation = value.get("trust_attestation")
    if not isinstance(attestation, dict) or attestation.get("verifier_id") != VERIFIER_ID:
        raise ValueError("observation was not signed by the configured independent verifier")
    if value.get("provenance_verified") is not False or value.get("evidence_credit") is not False:
        raise ValueError("verifier output must not self-award provenance or evidence credit")
    return value


def main() -> int:
    try:
        dsn = os.environ["JARVIS_DATABASE_URL"]
        account_id = os.environ["JARVIS_PAPER_ACCOUNT_ID"]
        public_key = os.environ.get("JARVIS_GATEIO_VERIFIER_PUBLIC_KEY_B64") or Path(
            "config/gateio-verifier-public-key.b64"
        ).read_text(encoding="utf-8").strip()
        observation_path = os.environ.get("JARVIS_ATTESTED_OBSERVATION_PATH")
        observation_url = os.environ.get(
            "JARVIS_ATTESTED_OBSERVATION_URL",
            "https://jarvis-gateio-attestor.beeniko33.workers.dev/v1/attestation",
        )
        import psycopg

        def connect():
            return psycopg.connect(
                dsn,
                connect_timeout=5,
                sslmode="require",
                options="-c statement_timeout=10000 -c lock_timeout=3000",
                application_name="jarvis-paper-cycle-runner",
            )

        controls = load_operator_controls(connect)
        # Production controls are read-only. A missing, stale, blocked, or paused
        # heartbeat exits before fetching market data or touching paper state.
        if (not isinstance(controls, dict)
                or controls.get("health") != "healthy"
                or controls.get("mode") != "paper"
                or controls.get("kill_switch_engaged") is not False
                or controls.get("entries_paused") is not False):
            print(json.dumps({
                "status": "blocked",
                "reason": "operator_controls_missing_stale_or_blocked",
                "mode": "paper",
                "order_authorized": False,
                "orders_submitted": 0,
                "execution_started": False,
            }, sort_keys=True))
            return 0
        if os.environ.get("JARVIS_RUNNER_PREFLIGHT_ONLY") == "1":
            print(json.dumps({
                "status": "preflight_only",
                "controls_present": isinstance(controls, dict),
                "health": controls.get("health") if isinstance(controls, dict) else None,
                "mode": controls.get("mode") if isinstance(controls, dict) else None,
                "kill_switch_engaged": controls.get("kill_switch_engaged") if isinstance(controls, dict) else None,
                "entries_paused": controls.get("entries_paused") if isinstance(controls, dict) else None,
                "market_fetch_performed": False,
                "paper_state_write_performed": False,
                "orders_submitted": 0,
            }, sort_keys=True))
            return 0
        observation = (
            load_attested_observation(observation_path)
            if observation_path else fetch_attested_observation(observation_url)
        )
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
