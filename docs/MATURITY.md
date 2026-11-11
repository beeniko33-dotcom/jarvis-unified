# Maturity Model — Jarvis Unified

Honest tracking only. No marketing claims.

| Level | Name | Meaning |
|---|---|---|
| **0** | Skeleton | Placeholder / incomplete ideas |
| **1** | Foundation | Clean structure, secrets hygiene, single config, runnable entry point |
| **2** | Operational tooling | Status API, passing CI, config checks, paper broker and risk-gated execution |
| **3** | Paper-validated | Sustained paper trading with measured signal quality and auditable results |
| **4** | Production | Hardened deployment, monitoring, operational risk controls, formal approvals and independent release review |

## Current status

**Level 2 — Operational tooling — last confirmed on main.**

This branch adds Level 3 measurement infrastructure. It does not yet qualify as Level 3: sustained multi-day evidence has not been collected or independently reviewed.

## Delivered foundation

- Paper-only config; kill switch engaged by default and not env-overridable
- Central risk gate + ExecutionService
- Paper broker with fills, realized PnL, mark-to-market equity, fees/slippage and JSONL audit ledger
- Ledger now records post-fill balance, equity, realized PnL and open-position count
- Localhost read-only status API and dashboard
- Portfolio tracker and SignalIntent contract
- Deriv/MT5 adapters disabled at construction
- SSRF-safe scraper fetch foundation
- Deterministic paper session runner and paper-ledger analytics report

## Level 3 evidence gates

- [ ] At least 30 consecutive calendar days of timestamped paper ledgers
- [ ] Signal-level attribution: strategy/version, data source, signal, entry/exit and rationale
- [ ] Reconciliation of fills, fees, PnL and all open positions
- [ ] Published win rate, expectancy, profit factor, maximum drawdown, slippage and rejected-entry rate
- [ ] Out-of-sample review, including losing periods and data gaps
- [ ] Zero unexplained positions and no live broker execution during validation

Run `python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30` to enforce the minimum date-span and flat-position checks. A single deterministic sample is a smoke test, not Level 3 validation.

## Remaining upgrades

- Durable broker-state recovery and ledger integrity/hash chaining
- Signal and strategy attribution plus real market-data provenance
- Daily loss accounting including unrealized PnL, daily reset/timezone policy, peak-equity drawdown, stale-price and correlated-exposure limits
- Scraper history-preserving import and feature-by-feature regression against the original repository
- Authenticated deployment, monitoring, incident response and independent security review (Level 4)

Live trading remains locked. No performance or profit is guaranteed.
