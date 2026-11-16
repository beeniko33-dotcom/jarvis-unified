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

## Current Deriv public-feed limitation

On 2026-11-14, a read-only smoke check against Deriv's documented public WebSocket returned an
`active_symbols` catalog with 95 entries but no canonical `FRXEURUSD` symbol. The collector
therefore failed closed before subscribing to ticks. The documented [`active_symbols`](https://developers.deriv.com/docs/data/active-symbols/)
and [`ticks`](https://developers.deriv.com/docs/data/ticks/) requests require an active symbol;
do not substitute another instrument or claim evidence until EUR/USD is actually listed and
the provider-provenance gate in issue #9 is independently resolved.

## Binance public spot market-data candidate

A read-only Binance Spot collector is available in `research/binance_public_feed.py`.
It uses Binance's documented market-data-only REST host (no API key) to fetch the
server clock and the newest **completed** candle for a configured spot symbol
(default `BTCUSDT`, `1m`). It rejects an open candle, malformed OHLC values,
unsupported symbols/interval syntax, and candles older than its freshness window.
The raw server-time/candle response is retained with a SHA-256 digest.

Example:

```bash
python -m research.binance_public_feed --symbol BTCUSDT --interval 1m
```

This is a read-only collector and one-shot observation writer, not a continuous
worker or a paper execution engine. It does not authenticate individual exchange
messages or independently prove provider provenance. Stored observations remain
`unverified_candidate`, `provenance_verified=false`, and
`evidence_credit=false`. No live order endpoint, account stream, API key, or broker
credential is used. Binance spot candles must not be relabelled as Deriv FX quotes.
The collector must pass CI and a separate operator-run read-only smoke check before
any strategy-to-paper-broker wiring is enabled. A completed-candle observation can
only drive a candle-close strategy, never a tick-scalping strategy.

## Evidence tooling: attribution, rejections, reconciliation, daily check

These tools measure and report. None of them place orders, change risk limits, release the kill
switch, or count toward the Level 3 gate by themselves.

```bash
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --observations-db var/paper_ledger.observations.sqlite3
python scripts/paper_reconcile.py var/paper_ledger.jsonl
python scripts/paper_daily_check.py var/paper_ledger.jsonl --observations-db var/paper_ledger.observations.sqlite3
```

- **Attribution.** Fills now write `strategy_id`, `strategy_version`, `quote_source` and the other
  sanitized lineage keys onto the JSONL row when the order carried them. `paper_session.py` labels its
  fills `paper_session_smoke` / `synthetic_fixture`: the prices are fixed, so they are never market
  evidence. Closing fills carry no lineage yet, so attribution coverage in a session is about 50%.
- **Rejected entries.** `paper_session.py` journals every risk decision into a hash-chained SQLite
  journal (`<ledger>.observations.sqlite3`). `paper_report.py --observations-db` verifies the chain
  and reports the rejected-entry rate (rejected entries over decided entries). Without the flag the
  rate is reported as unavailable, as before.
- **Reconciliation.** `paper_reconcile.py` replays fills from scratch and compares realized P&L,
  commission, balance and open-position count with every recorded row. It is exact for immediate
  full fills; working or partially filled orders are reported as unsupported and the result is
  `incomplete`, never `reconciled`. A match shows internal consistency only, not data authenticity.
- **Daily check.** `paper_daily_check.py` reports missing days, a broken streak, future-dated events,
  open positions, reconciliation status and journal integrity, and exits non-zero when any need
  operator attention. Its streak is informational and always reports that it does not count toward
  Level 3. Run it from your own scheduler; it never backfills or repairs.

### Known limitation: appended sessions are not one account

`paper_session.py` builds a fresh broker on every run, so each run restarts at the starting balance
with zeroed cumulative figures, but it appends to the same ledger file. A file built by running it
daily is therefore several independent accounts, not one continuous account. `paper_reconcile.py`
detects this (cumulative commission falls) and says so in `suspected_session_boundaries`, and the
daily check will report the ledger as not reconciled. Until the runner uses a persistent account, use
a fresh dated ledger per session or the persistent SQLite broker for multi-day validation.
