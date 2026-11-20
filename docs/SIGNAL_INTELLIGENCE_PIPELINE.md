# Forex signal intelligence and forecast pipeline

**Product mode:** signal and forecast analytics only. No paper trading, demo trading, broker execution, positions, account balances, order sizing or trade lifecycle.

## Data sources and trust
| Source | Intended use | Trust treatment |
|---|---|---|
| Deriv public feed | Candidate FX quote observations for supported instruments | Verify actual catalog and provenance; label unverified until independently established |
| Biquote | Secondary candidate quote stream | Candidate/unverified until source lineage is validated |
| Twelve Data | Independent reference/reconciliation where access permits | Respect plan cadence and entitlement |
| Gate.io | Excluded from Forex forecasts; crypto is a different asset class | Never substitute crypto spot for OTC FX |

Never infer an instrument code. Store provider timestamp, collector receive time, source identifier, bid/ask where available, quote age, spread and validation result. Reject malformed, stale, future-dated, out-of-order or wrong-symbol observations.

## Forecast output
Each forecast contains instrument, timeframe, horizon, generation timestamp, bullish/bearish/neutral direction, explainable strength score (not a probability), data-quality status, rationale and strategy version. The current reference engine uses short/long EMA relationship and recent momentum, requires at least 20 chronological fresh candles, and makes no calibrated probability claim.

The engine does not produce entry levels, stop-loss, take-profit, lot size, leverage, position size, orders, fills or execution assumptions.

## Operational requirements
1. Obtain market data from an explicitly approved source and preserve source attribution.
2. Normalize FX symbols, timezone-aware timestamps and OHLC/quote values.
3. Reject invalid or stale data rather than carrying forward old prices.
4. Generate reproducible forecasts with strategy/version metadata.
5. Persist immutable forecast snapshots and later observed outcomes.
6. Evaluate directional accuracy, calibration, coverage and false-signal rate by instrument/timeframe. Do not publish a confidence probability until calibrated out-of-sample.
7. Alert users to new, changed, expired or invalidated forecasts; require opt-in and support quiet hours/unsubscribe.
8. Display a clear research-only disclaimer and distinguish verified observations from unverified candidate data.

## Security and reliability
Authentication, authorization, input validation, rate limits, audit logs, secret isolation, tenant isolation and source integrity checks remain enabled. Removing trading features does not mean removing application security or data-quality checks.

## Migration status
The new forecast engine and tests are introduced on the signal-only feature branch. Existing paper/trading code, database objects and historical workflows have not yet been physically removed from the repository or production. Complete conversion requires removing legacy trading imports, command-line actions, API routes, UI components, migrations, scheduled workflows, secrets and dashboard labels, then running repository-wide checks and full CI. No production database or deployment is changed by this branch.
