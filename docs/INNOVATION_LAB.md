# Jarvis Innovation Lab

The Innovation Lab evaluates strategy experiments without executing them.

## Experiment lifecycle

1. Create an immutable experiment record with strategy/version identifiers.
2. Record the data source, data hash, sample window, and whether provenance is independently verified.
3. Evaluate on a holdout/out-of-sample window; include spreads, commissions, slippage, and other applicable transaction costs.
4. Compare candidate net return and drawdown with a fixed baseline.
5. Reject weak candidates. Keep incomplete or unverified evidence in research-only status.
6. A candidate that meets the configured thresholds is marked **human review required**. It is never auto-promoted and never receives broker permissions.

## Current foundation

`research/innovation_lab.py` provides a deterministic assessment function. It is deliberately not wired into the runtime strategy registry or `ExecutionService`. Its tests cover provenance, out-of-sample status, transaction costs, sample size, return improvement, and drawdown.

## Important limits

- Synthetic, replayed, or unverified market data cannot be represented as verified provider evidence.
- A backtest or experiment result is not proof of future profitability.
- Passing this assessment is not Level 3 certification, Level 4 readiness, or authorization to trade.
- Any later promotion workflow must require independent review, immutable experiment artifacts, and a separate explicit operator action.
