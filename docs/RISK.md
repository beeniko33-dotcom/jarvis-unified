# Risk Engine — Initial Rules

Every order must pass the central risk gate. Defaults: per-order notional cap 5 account-currency units; daily realized-loss cap 10; maximum two open positions; kill switch engaged by default. Invalid orders fail closed.

This initial engine does not yet model unrealized PnL, margin, leverage, correlated exposure, fees, slippage, gaps, or broker liquidation. Do not connect real accounts.

Before demo adapters, add daily reset/timezone policy, persistent audit logs, per-symbol exposure, stop-loss/take-profit lifecycle, trailing stops, drawdown limits, stale-price rejection, order reconciliation, and disconnect handling.