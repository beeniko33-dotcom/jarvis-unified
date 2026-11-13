# 1,000-cycle paper stress test

Run from the repository root:

```bash
python scripts/paper_stress.py --cycles 1000
```

Each cycle uses an isolated temporary SQLite database and deterministic synthetic
prices. It creates a working order, applies a partial fill, reconstructs the broker
from disk, replays the same fill ID to check idempotency, completes the order, closes
the simulated position, and verifies the audit hash chain and flat end state.

The temporary databases are discarded after the run and are never written to the
forward-validation ledger. No market data, Deriv/MT5 adapter, wallet, network order
endpoint, or live account is accessed.

A successful run is a software durability/stress result only. It earns **zero Level 3
forward-validation days**. Level 3 still requires at least 30 consecutive calendar
days of genuine timestamped paper observations, complete fill/cost reconciliation,
out-of-sample review, zero unexplained positions, and independent human review.
Synthetic observations must never be used to satisfy those gates.
