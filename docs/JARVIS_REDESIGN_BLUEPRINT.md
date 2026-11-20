# Jarvis Unified — signal-only product direction

## Product decision

Jarvis Unified is a Forex market intelligence product. It collects and validates FX market data, produces explainable directional forecasts, evaluates historical forecast quality and sends user-configured alerts.

There is no trading product surface: no live, demo or paper trading; no broker orders; no execution adapters; no positions, account balances, leverage or position sizing; no entry/stop/target instructions; and no execution kill-switch or entry-pause controls.

## Core features

1. Multi-source FX market observation with explicit provenance, freshness, spread and quality labels.
2. Multi-timeframe trend, momentum, volatility and market-session analysis.
3. Bullish, bearish or neutral directional forecasts with rationale and a heuristic strength score.
4. Forecast history, expiry, revisions and invalidation tracking.
5. Historical evaluation by instrument and timeframe, including accuracy, coverage, false-signal rate and calibration.
6. Watchlists and opt-in notifications for new or materially changed forecasts.
7. Read-only dashboards, source health, data-quality incidents and service status.

## Forecast integrity

A forecast is research information, not a trade instruction. Strength scores must not be presented as probabilities until calibrated and validated out of sample. Never fabricate missing prices or instrument mappings. Reject stale, future-dated, malformed or out-of-order market observations. Preserve provider timestamps separately from collection timestamps and label unverified sources honestly.

## Data provider boundaries

Deriv public market data may be used only for instruments confirmed by the provider's live catalog. Gate.io is crypto spot and is excluded from conventional FX forecasting. Other reference feeds must be used within their documented access and rate limits. No broker account credentials are required for public market analysis.

## Security and operations

Authentication, authorization, secret isolation, source validation, audit logs, rate limits, tenant isolation, opt-in notifications and unsubscribe remain mandatory. “Remove blockage” means remove obsolete trading-mode and execution gates from the product; it does not mean disable security or data-integrity protections.

## Migration work

The dedicated signal-only branch adds an analytics-only forecast engine, tests, a JSON-candle CLI and revised product/pipeline documentation. Legacy paper/trading modules, API routes, UI components, database tables and scheduled workflows are still present in the repository and have not been removed from production. Full conversion requires a repository-wide dependency map and tested deletion/migration of those components before release.

## Release boundary

This change is feature-branch work only. No production database, Cloudflare Worker, Pages production deployment, broker account or user notification subscription is modified.
