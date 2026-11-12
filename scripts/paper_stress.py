"""Deterministic paper-broker durability stress test; never connects to a market or broker."""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from brokers.paper import PersistentPaperBroker
from core.models import OrderRequest, Side


def run_stress(cycles: int = 1000) -> dict:
    if cycles < 1:
        raise ValueError("cycles must be positive")

    completed = 0
    with tempfile.TemporaryDirectory(prefix="jarvis-paper-stress-") as root:
        root_path = Path(root)
        fixed_clock = lambda: datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

        for index in range(cycles):
            # Isolated synthetic database: never contaminates forward evidence.
            database = root_path / f"cycle-{index:04d}.sqlite3"
            symbol = f"SIM{index:04d}"
            broker = PersistentPaperBroker(
                Decimal("10000"), database_path=database,
                commission_per_side=Decimal("0"), slippage_bps=Decimal("0"),
                clock=fixed_clock,
            )
            opened = broker.place_working_order(
                OrderRequest(symbol, Side.BUY, Decimal("2"), Decimal("10"),
                             f"stress-client-{index}")
            )
            first = broker.apply_partial_fill(
                opened.order_id, Decimal("1"), fill_id=f"stress-fill-{index}-a"
            )

            # Reconstruct from disk; this is a new broker object and SQLite reload.
            broker = PersistentPaperBroker(
                Decimal("10000"), database_path=database, clock=fixed_clock
            )
            duplicate = broker.apply_partial_fill(
                opened.order_id, Decimal("1"), fill_id=f"stress-fill-{index}-a"
            )
            if duplicate.filled_quantity != first.filled_quantity:
                raise AssertionError(f"cycle {index}: duplicate fill changed state")

            final = broker.apply_partial_fill(
                opened.order_id, Decimal("1"), fill_id=f"stress-fill-{index}-b"
            )
            if final.status != "filled" or final.filled_quantity != Decimal("2"):
                raise AssertionError(f"cycle {index}: order did not complete exactly once")

            broker.close_position(symbol, Decimal("10"))
            if broker.get_positions():
                raise AssertionError(f"cycle {index}: unexplained open position remains")
            if not broker.reconcile().get("chain_ok"):
                raise AssertionError(f"cycle {index}: audit hash chain failed")
            completed += 1

    return {
        "mode": "synthetic_paper_stress",
        "cycles_requested": cycles,
        "cycles_completed": completed,
        "restart_recoveries": completed,
        "duplicate_fill_replays_checked": completed,
        "flat_positions_at_cycle_end": completed,
        "audit_chains_verified": completed,
        "market_data_used": False,
        "live_broker_or_order_endpoint_used": False,
        "forward_validation_evidence": False,
        "level_3_days_credited": 0,
        "result": "passed",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(run_stress(args.cycles), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
