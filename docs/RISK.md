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

- The paper broker remains in-memory. Open positions, idempotency keys and PnL state do not
  survive process restart; a JSONL ledger is an audit trail, not a recovery/reconciliation engine.
- The current broker PnL is cumulative for the running process, not a correctly reset UTC-day
  PnL series. The configured loss limit is therefore a conservative process-session guard,
  not a certified daily-loss control. Restarting the process resets that in-memory state.
- The risk gate uses requested notional and does not yet model margin, leverage, spread or
  slippage-adjusted notional.
- No correlated exposure, per-symbol caps, stale quote timestamps or peak-equity drawdown
  control is implemented.
- A service-level lock protects callers sharing one ExecutionService instance; it is not a
  cross-process lock or a substitute for broker-side atomic reservations.

Do not connect real accounts. Persistent recovery, UTC daily accounting, quote freshness,
slippage-aware sizing, drawdown controls and multi-process coordination must be designed and
tested before any future adapter is considered.
