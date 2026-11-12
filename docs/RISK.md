# Risk Engine — Rules

Every new entry must pass the central risk gate. Risk-reducing closes remain available while
the entry kill switch is engaged.

## Current hard limits (defaults)

| Control | Default | Notes |
|---------|---------|-------|
| Per-order notional | 5 account-currency units | requested quantity × requested price |
| Loss limit | 10 | net realized + unrealized PnL, less commissions |
| Max open positions | 2 | count of symbols with open exposure |
| Kill switch | **Engaged** | cannot be disabled via environment variables |

Invalid orders fail closed. Non-paper modes are rejected at config load.

## Implemented

- Fail-closed evaluation and explicit operator action to release the kill switch.
- ExecutionService serializes account snapshot, risk decision and broker submission so
  concurrent calls through the same service instance cannot all pass on a stale position count.
- New entries are blocked on net marked PnL: realized PnL + unrealized PnL − commissions.
- Paper broker exposes commission totals in its account snapshot.
- Deriv and MT5 adapters remain disabled.

## Important limitations

- The default `PaperBroker` remains in-memory for fast deterministic tests. The opt-in
  `PersistentPaperBroker` stores positions, orders, client-order idempotency keys, balance,
  realized PnL, commissions and marks in SQLite. Its state updates and SHA-256 chained audit
  events commit in one `BEGIN IMMEDIATE` transaction.
- `PersistentPaperBroker` reconstructs state after restart, verifies every audit-chain link,
  and compares the current snapshot with the latest event. Missing, altered or inconsistent
  state fails closed by raising an integrity error.
- The persistent broker derives UTC-day realized PnL and commissions from timestamped events.
  `ExecutionService` uses those day-scoped totals when the broker advertises daily accounting;
  the in-memory broker retains process-session accounting and is explicitly marked as such.
- SQLite writer transactions serialize reservations across broker instances/processes. This
  does not provide distributed coordination across separate database files or hosts.
- The risk gate uses requested notional and does not yet model margin, leverage, spread or
  slippage-adjusted notional.
- Stale-quote rejection, provider quote provenance, per-symbol/correlated exposure limits,
  peak-equity drawdown controls and crash-injection testing remain outstanding.
- A service-level lock protects callers sharing one ExecutionService instance; it is not a
  cross-process lock or a substitute for broker-side atomic reservations.

Do not connect real accounts. Persistent recovery, UTC daily accounting, quote freshness,
slippage-aware sizing, drawdown controls and multi-process coordination must be designed and
tested before any future adapter is considered.
