#!/usr/bin/env python3
"""Run a short deterministic paper session for audit logging (Level 3 prep).

Does not enable live trading. Kill switch must be released only via explicit operator flag in code for entries; this script demonstrates risk-gated flow.
"""
from __future__ import annotations

import argparse
import json
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Jarvis Unified paper session runner")
    parser.add_argument("--ledger", default="var/paper_ledger.jsonl", help="JSONL audit path")
    parser.add_argument("--balance", default="10000", help="Starting paper balance")
    parser.add_argument("--allow-entries", action="store_true", help="Explicitly release kill switch for this session")
    args = parser.parse_args()

    ledger = Path(args.ledger)
    broker = PaperBroker(
        Decimal(args.balance),
        commission_per_side=Decimal("0.1"),
        slippage_bps=Decimal("5"),
        ledger_path=ledger,
    )
    risk = RiskEngine(RiskLimits(Decimal("50"), Decimal("100"), 5, True))
    if args.allow_entries:
        risk.release_kill_switch(explicit_operator_action=True)

    exec_svc = ExecutionService(broker, risk)
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

    orders = [
        OrderRequest("EURUSD", Side.BUY, Decimal("1"), Decimal("1.10"), "sess-1"),
        OrderRequest("GBPUSD", Side.BUY, Decimal("1"), Decimal("1.25"), "sess-2"),
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
    print(json.dumps({"ok": True, "events": events, "ledger": str(ledger)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
