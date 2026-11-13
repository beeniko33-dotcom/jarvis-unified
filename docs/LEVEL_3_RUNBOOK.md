# Level 3 Paper Validation Runbook

Jarvis is **Level 2 operational tooling** until real, timestamped paper observations satisfy the validation gates below. The code additions in this branch improve measurement; they do not manufacture a Level 3 result.

## Generate an auditable paper session

```bash
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl
```

The entry flag releases the in-memory paper risk gate for that one process only. It does not change environment configuration, connect to Deriv/MT5, or authorize real orders. Use a fresh ledger for a new controlled experiment; archive old ledgers rather than overwriting them.

## What the report measures

- Consecutive UTC calendar days with ledger events (gaps are reported and break the run)
- Realized PnL changes observed at fills
- Win/loss event counts, win rate and expectancy
- Gross profit/loss and profit factor when losses exist
- Maximum observed equity drawdown from the recorded equity snapshots
- Notional-weighted modeled slippage when raw and fill prices are present
- Ending equity, balance and open-position count

These are descriptive event-level metrics. Partial closes are separate realized events; this is not yet a strategy-level trade attribution engine. The report cannot establish signal quality without strategy IDs and independently verified market data.
The fill-only ledger does not include rejected-entry decisions, so it reports rejected-entry rate as unavailable rather than assuming zero. Attribution coverage counts rows with strategy ID, strategy version, and quote source. The current broker does not persist those metadata fields, so fill rows are unattributed. The fill ledger also cannot prove market-data observation on a day without fills; preserve a separate timestamped daily data-quality/operations record for those days.

## Minimum evidence before claiming Level 3

1. Run at least 30 consecutive calendar days in paper mode with timestamped, append-only ledgers.
2. Record the strategy/version, signal timestamp, market-data source, spread, intended risk, entry/exit rationale and execution costs for each decision.
3. Reconcile every fill, fee, realized PnL and open position; finish with zero unexplained positions.
4. Publish win rate, expectancy, profit factor, maximum drawdown, rejected-entry rate, slippage and sample size, including losing periods.
5. Review results out-of-sample and investigate data gaps, duplicate orders and abnormal execution.
6. Keep the kill switch and live broker adapters locked throughout validation.

A short deterministic sample is a smoke test, not sustained validation. No profit is guaranteed. A green CI run proves software checks, not trading performance.

The report normalizes explicitly timezone-aware timestamps to UTC and rejects
out-of-order events. `--min-days 30` requires a consecutive run of 30 UTC dates
with ledger events; distinct dates separated by gaps do not count as a run.

## Research replay engine

See `docs/LEVEL_3_RESEARCH_ENGINE.md` for the historical-data replay workflow, CSV contract, strategy version, SQLite durability and event-chain checks. This supplements, but does not replace, the 30-day forward paper-validation requirements.
