"""One-shot Postgres-backed research-cycle orchestrator.

This module commits research/audit decisions only. It has no exchange client,
order interface, wallet signer, or control-state mutation capability. The
independent verifier supplies a signed normalized Gate.io observation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from research.paper_cycle_engine import plan_cycle
from research.supabase_paper_state import SupabasePaperStateStore


def run_once(
    *,
    store: SupabasePaperStateStore,
    account_id: str,
    observation: dict[str, Any],
    controls: dict[str, Any] | None,
    trusted_verifier_public_key: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate one signed observation and atomically persist one research decision.

    Blocked observations do not write a run, snapshot, or ledger event. A stable
    UUID derived from account + planner fingerprint makes retries idempotent.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("orchestrator clock must be timezone-aware")

    decision = plan_cycle(
        observation,
        controls,
        trusted_verifier_public_key=trusted_verifier_public_key,
        now=current,
    )
    if decision["status"] != "eligible_for_research_decision":
        return {
            "status": "blocked",
            "reasons": decision["reasons"],
            "candidate": "BLOCKED",
            "committed": False,
            "mode": "paper",
            "order_authorized": False,
            "orders_submitted": 0,
            "execution_started": False,
        }

    # load_account verifies both snapshot hash and the complete event/run chain.
    account = store.load_account(account_id)
    revision = account["revision"] if account else 0
    state = dict(account["state"]) if account else {"schema_version": 1}
    state["last_research_decision"] = {
        "candidate": decision["candidate"],
        "indicators": decision["indicators"],
        "input_fingerprint": decision["input_fingerprint"],
        "strategy_id": decision["strategy_id"],
        "strategy_version": decision["strategy_version"],
        "decided_at": current.astimezone(timezone.utc).isoformat(),
    }

    fingerprint = {
        "planner_fingerprint": decision["input_fingerprint"],
        "strategy_id": decision["strategy_id"],
        "strategy_version": decision["strategy_version"],
        "observation_source": observation["source"],
        "instrument": observation["instrument"],
        "event_time": observation["event_time"],
    }
    run_id = str(uuid5(
        NAMESPACE_URL,
        "jarvis-paper-research:" + account_id + ":" + decision["input_fingerprint"],
    ))
    committed = store.commit_cycle(
        account_id=account_id,
        run_id=run_id,
        expected_revision=revision,
        state=state,
        events=[{
            "event_type": "research.decision",
            "occurred_at": current,
            "payload": {
                "candidate": decision["candidate"],
                "indicators": decision["indicators"],
                "input_fingerprint": decision["input_fingerprint"],
                "trust_attestation_verified": True,
                "order_authorized": False,
                "orders_submitted": 0,
            },
        }],
        input_fingerprint=fingerprint,
        metadata={
            "runtime": "jarvis-postgres-paper-cycle-orchestrator",
            "mode": "paper",
            "strategy_id": decision["strategy_id"],
            "strategy_version": decision["strategy_version"],
            "execution_started": False,
        },
    )
    return {
        "status": "committed",
        "candidate": decision["candidate"],
        "run_id": committed["run_id"],
        "revision": committed["revision"],
        "run_revision": committed["run_revision"],
        "duplicate": committed["duplicate"],
        "state_sha256": committed["state_sha256"],
        "mode": "paper",
        "order_authorized": False,
        "orders_submitted": 0,
        "execution_started": False,
    }
