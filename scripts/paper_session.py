#!/usr/bin/env python3
"""Run a short deterministic paper session for audit logging (Level 3 prep).

Does not enable live trading. Kill switch must be released only via explicit operator flag in code for entries; this script demonstrates risk-gated flow.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brokers.paper import PaperBroker
from core.execution import ExecutionService
from core.models import OrderRequest, Side
from core.portfolio import PortfolioTracker
from core.risk import RiskEngine, RiskLimits
from research.execution_observations import ExecutionObservationJournal

# Honest labels: this runner replays fixed prices, so its fills are never market evidence.
SESSION_LINEAGE = {
    "research_lineage": {
        "strategy_id": "paper_session_smoke",
        "strategy_version": "1",
        "quote_source": "synthetic_fixture",
    }
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Jarvis Unified paper session runner")
    parser.add_argument("--ledger", default="var/paper_ledger.jsonl", help="JSONL audit path")
    parser.add_argument("--balance", default="10000", help="Starting paper balance")
    parser.add_argument("--allow-entries", action="store_true", help="Explicitly release kill switch for this session")
    parser.add_argument(
        "--observations-db",
        default=None,
        help="hash-chained SQLite journal of risk decisions and rejections "
        "(default: <ledger>.observations.sqlite3)",
    )
    args = parser.parse_args()

    ledger = Path(args.ledger)
    observations_db = (
        Path(args.observations_db)
        if args.observations_db
        else ledger.with_suffix(".observations.sqlite3")
    )
    broker = PaperBroker(
        Decimal(args.balance),
        commission_per_side=Decimal("0.1"),
        slippage_bps=Decimal("5"),
        ledger_path=ledger,
    )
    risk = RiskEngine(RiskLimits(Decimal("50"), Decimal("100"), 5, True))
    if args.allow_entries:
        risk.release_kill_switch(explicit_operator_action=True)

    journal = ExecutionObservationJournal(observations_db)
    exec_svc = ExecutionService(broker, risk, observation_journal=journal)
    tracker = PortfolioTracker(broker)

    events: list[dict] = []

    def record(label: str, **extra):
        snap = tracker.snapshot()
        events.append(
            {
                "event": label,
                "balance": str(snap.account.balance),
                "equity": str(snap.account.equity),
                "realized_pnl": str(snap.account.realized_pnl),
                "open_positions": snap.account.open_positions,
                **extra,
            }
        )

    record("session_start", kill_switch=risk.halted)

    # Unique per run: the observation journal refuses reused client order IDs,
    # and one journal accumulates every daily session.
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    orders = [
        OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), f"sess-{session_id}-1", dict(SESSION_LINEAGE)),
        OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("1.25"), f"sess-{session_id}-2", dict(SESSION_LINEAGE)),
    ]

    for order in orders:
        try:
            result = exec_svc.submit(order)
            record("fill", symbol=result.symbol, side=result.side.value, fill=str(result.fill_price))
        except PermissionError as exc:
            record("rejected", reason=str(exc), symbol=order.symbol)

    # Mark-to-market move
    broker.set_last_prices({"EURUSD": Decimal("1.12"), "GBPUSD": Decimal("1.24")})
    record("mtm_update")

    # Close if any open
    for pos in broker.get_positions():
        try:
            exit_prices = {"EURUSD": Decimal("1.12"), "GBPUSD": Decimal("1.24")}
            result = exec_svc.close_position(pos.symbol, exit_prices[pos.symbol])
            record("close", symbol=result.symbol, fill=str(result.fill_price))
        except Exception as exc:  # noqa: BLE001
            record("close_error", symbol=pos.symbol, reason=str(exc))

    record("session_end")
    print(
        json.dumps(
            {
                "ok": True,
                "events": events,
                "ledger": str(ledger),
                "observations_db": str(observations_db),
                "observations_chain_verified": journal.verify(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
