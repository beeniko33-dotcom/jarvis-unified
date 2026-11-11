# Level 3 Paper Validation Runbook

Jarvis is **Level 2 operational tooling** until real, timestamped paper observations satisfy the validation gates below. The code additions in this branch improve measurement; they do not manufacture a Level 3 result.

## Generate an auditable paper session

```bash
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl
```

The entry flag releases the in-memory paper risk gate for that one process only. It does not change environment configuration, connect to Deriv/MT5, or authorize real orders. Use a fresh ledger for a new controlled experiment; archive old ledgers rather than overwriting them.

## What the report measures

- Distinct UTC calendar days represented in the ledger
- Realized PnL changes observed at fills
- Win/loss event counts, win rate and expectancy
- Gross profit/loss and profit factor when losses exist
- Maximum observed equity drawdown from the recorded equity snapshots
- Ending equity, balance and open-position count

These are descriptive event-level metrics. Partial closes are separate realized events; this is not yet a strategy-level trade attribution engine. The report cannot establish signal quality without strategy IDs and independently verified market data.

## Minimum evidence before claiming Level 3

1. Run at least 30 consecutive calendar days in paper mode with timestamped, append-only ledgers.
2. Record the strategy/version, signal timestamp, market-data source, spread, intended risk, entry/exit rationale and execution costs for each decision.
3. Reconcile every fill, fee, realized PnL and open position; finish with zero unexplained positions.
4. Publish win rate, expectancy, profit factor, maximum drawdown, rejected-entry rate, slippage and sample size, including losing periods.
5. Review results out-of-sample and investigate data gaps, duplicate orders and abnormal execution.
6. Keep the kill switch and live broker adapters locked throughout validation.

A short deterministic sample is a smoke test, not sustained validation. No profit is guaranteed. A green CI run proves software checks, not trading performance.


## Research replay engine

See `docs/LEVEL_3_RESEARCH_ENGINE.md` for the historical-data replay workflow, CSV contract, strategy version, SQLite durability and event-chain checks. This supplements, but does not replace, the 30-day forward paper-validation requirements.


## Forward evidence collector (new)

The forward evidence collector stores externally sourced, timestamped paper observations
in a durable SQLite database and calculates the uninterrupted UTC-day streak ending on the
latest observation date. It rejects timezone-naive timestamps and configuration mismatches,
deduplicates identical instrument/interval/timestamp observations, and verifies a SHA-256
append-only chain.

See `docs/LEVEL_3_FORWARD_VALIDATION.md`.

The collector does not fetch market data or place orders. The operator must supply licensed,
authorized provider observations and retain original provider payloads. A 30-day coverage-gate
pass is not Level 3 certification. CI fixtures and historical replay do not count.
