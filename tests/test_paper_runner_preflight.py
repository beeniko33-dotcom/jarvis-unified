from research.paper_runner_preflight import assess_preflight


def controls(**changes):
    row = {
        "worker_id": "cloudflare-control-worker",
        "health": "healthy",
        "mode": "paper",
        "kill_switch_engaged": False,
        "entries_paused": False,
    }
    row.update(changes)
    return row


def verified_ledger():
    return {"verified": True, "events": 0, "tail_hash": "GENESIS"}


def test_engaged_kill_switch_blocks_preflight():
    report = assess_preflight(
        controls(kill_switch_engaged=True),
        None,
        verified_ledger(),
        cycle_engine_available=True,
    )
    assert report["status"] == "blocked"
    assert "kill_switch_not_confirmed_released" in report["reasons"]


def test_paused_entries_block_preflight():
    report = assess_preflight(
        controls(entries_paused=True),
        None,
        verified_ledger(),
        cycle_engine_available=True,
    )
    assert "entries_not_confirmed_unpaused" in report["reasons"]


def test_missing_or_unhealthy_controls_fail_closed():
    missing = assess_preflight(None, None, verified_ledger(), cycle_engine_available=True)
    unhealthy = assess_preflight(
        controls(health="blocked"), None, verified_ledger(), cycle_engine_available=True
    )
    assert missing["status"] == "blocked"
    assert "operator_control_row_missing" in missing["reasons"]
    assert "operator_health_not_healthy" in unhealthy["reasons"]


def test_unverified_ledger_and_non_paper_account_block():
    report = assess_preflight(
        controls(),
        {"mode": "live"},
        {"verified": False},
        cycle_engine_available=True,
    )
    assert "account_mode_not_paper" in report["reasons"]
    assert "paper_ledger_not_verified" in report["reasons"]


def test_preflight_never_claims_execution_or_orders():
    report = assess_preflight(controls(), None, verified_ledger())
    assert report["status"] == "blocked"
    assert "paper_cycle_engine_not_implemented" in report["reasons"]
    assert report["cycle_execution_started"] is False
    assert report["orders_submitted"] == 0
