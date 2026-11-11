# Risk Engine — Rules

Every **new entry** must pass the central risk gate (`core.risk.RiskEngine`). Risk-reducing closes remain available while the entry kill switch is engaged.

## Current hard limits (defaults)

| Control | Default | Notes |
|---------|---------|-------|
| Per-order notional | 5 account-currency units | `quantity * price` |
| Daily realized loss | 10 | Blocks new entries when `realized_pnl <= -limit` |
| Max open positions | 2 | Count of symbols with open exposure |
| Kill switch | **Engaged** | Cannot be disabled via environment variables |

Invalid orders fail closed. Non-paper modes are rejected at config load.

## Implemented

- Fail-closed evaluation
- Explicit operator action required to release kill switch
- ExecutionService always calls risk before `place_order`
- Paper broker fees/slippage do not bypass risk notional checks (risk uses request price × qty)

## Not yet modeled (before demo adapters)

- Unrealized PnL in daily loss calculation
- Margin / leverage
- Correlated exposure / per-symbol caps
- Daily reset / timezone policy
- Stale-price rejection
- Drawdown limits from peak equity
- Order reconciliation against external brokers
- Disconnect / partial-fill handling for live adapters

Do not connect real accounts until these are designed, tested under paper conditions, and explicitly approved.
