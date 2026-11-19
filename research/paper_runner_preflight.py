"""Read-only startup gate for the future supervised Postgres paper runner.

This module deliberately does not execute cycles, create ledger rows, or submit orders.
It verifies the operator control row and durable paper account before a separate,
reviewed cycle engine can be introduced.
"""
from __future__ import annotations

import json
import os
from contextlib import closing
from typing import Any

from research.supabase_paper_state import SupabasePaperStateStore


DEFAULT_WORKER_ID = "cloudflare-control-worker"


def assess_preflight(
    control_row: dict[str, Any] | None,
    account: dict[str, Any] | None,
    ledger: dict[str, Any] | None,
    *,
    cycle_engine_available: bool = False,
) -> dict[str, Any]:
    """Return a fail-closed readiness report without authorizing execution."""
    reasons: list[str] = []
    if control_row is None:
        reasons.append("operator_control_row_missing")
    else:
        if control_row.get("mode") != "paper":
            reasons.append("operator_mode_not_paper")
        if control_row.get("kill_switch_engaged") is not False:
            reasons.append("kill_switch_not_confirmed_released")
        if control_row.get("entries_paused") is not False:
            reasons.append("entries_not_confirmed_unpaused")
        if control_row.get("health") != "healthy":
            reasons.append("operator_health_not_healthy")

    if account is None:
        reasons.append("paper_account_missing")
    elif account.get("mode") != "paper":
        reasons.append("account_mode_not_paper")
    if ledger is None or ledger.get("verified") is not True:
        reasons.append("paper_ledger_not_verified")
    if not cycle_engine_available:
        reasons.append("paper_cycle_engine_not_implemented")

    return {
        "status": "blocked" if reasons else "preflight_ready",
        "reasons": reasons,
        "operator_controls_verified": control_row is not None and not any(
            reason in reasons for reason in (
                "operator_mode_not_paper",
                "kill_switch_not_confirmed_released",
                "entries_not_confirmed_unpaused",
                "operator_health_not_healthy",
            )
        ),
        "account_present": account is not None,
        "ledger_verified": ledger is not None and ledger.get("verified") is True,
        "cycle_execution_started": False,
        "orders_submitted": 0,
        "mode": "paper",
    }


def read_operator_control(store: SupabasePaperStateStore, worker_id: str) -> dict[str, Any] | None:
    """Read the latest single operator row; never mutate control state."""
    with closing(store._connect()) as db:
        with db:
            with db.cursor() as cur:
                cur.execute(
                    """select worker_id, health, mode, kill_switch_engaged, entries_paused
                       from public.operator_status where worker_id = %s order by reported_at desc limit 2""",
                    (worker_id,),
                )
                rows = cur.fetchall()
    if len(rows) != 1:
        return None
    worker, health, mode, kill_switch, entries_paused = rows[0]
    return {
        "worker_id": worker,
        "health": health,
        "mode": mode,
        "kill_switch_engaged": kill_switch,
        "entries_paused": entries_paused,
    }


def run_preflight(
    store: SupabasePaperStateStore,
    account_id: str,
    worker_id: str = DEFAULT_WORKER_ID,
) -> dict[str, Any]:
    """Verify operator state and the complete account ledger using read-only queries."""
    controls = read_operator_control(store, worker_id)
    account = store.load_account(account_id)
    # load_account verifies the chain when an account exists. For a not-yet-created
    # disposable account, verify_ledger confirms there are no orphaned rows.
    ledger = store.verify_ledger(account_id)
    return assess_preflight(controls, account, ledger, cycle_engine_available=False)


def main() -> int:
    account_id = os.environ.get("JARVIS_PAPER_ACCOUNT_ID")
    if not account_id:
        print(json.dumps({"status": "blocked", "reasons": ["JARVIS_PAPER_ACCOUNT_ID_missing"],
                          "cycle_execution_started": False, "orders_submitted": 0}))
        return 2
    try:
        store = SupabasePaperStateStore()
        report = run_preflight(store, account_id)
    except Exception as exc:  # noqa: BLE001 - never print DSNs or raw database errors
        report = {
            "status": "blocked",
            "reasons": ["preflight_failed_" + type(exc).__name__],
            "cycle_execution_started": False,
            "orders_submitted": 0,
            "mode": "paper",
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "preflight_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
