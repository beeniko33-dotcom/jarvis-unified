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

**Level 2 — Operational tooling — confirmed on `main`.**

Confirmed after CI-backed paper runtime, risk gate, kill switch, disabled live adapters, and merged persistent paper ledger / UTC risk work (PRs #12, #7).

**Level 3 is not certified.** Synthetic stress (including 1,000-cycle harnesses), historical replay, and CI fixtures do **not** count as Level 3 evidence.

**Level 4 is not started** as a certification target.

## Delivered on main (Level 2+)

- Paper-only config; kill switch engaged by default and not env-overridable
- Central risk gate + ExecutionService
- Paper broker with fills, realized PnL, mark-to-market equity, fees/slippage and JSONL audit ledger
- Restart-safe persistent paper ledger (SQLite WAL, hash-chained events, UTC-day accounting)
- Peak-equity drawdown and per-symbol exposure controls
- Localhost read-only status API and dashboard
- Portfolio tracker and SignalIntent contract
- Deriv/MT5 adapters disabled at construction
- SSRF-safe scraper fetch foundation
- Deterministic paper session runner and paper-ledger analytics report
- Unit/CI foundation diagnostic (`scripts/diagnose.py`)

## Level 3 evidence gates (all required)

- [ ] At least 30 consecutive calendar days of timestamped paper ledgers
- [ ] Signal-level attribution: strategy/version, data source, signal, entry/exit and rationale
- [ ] Reconciliation of fills, fees, PnL and all open positions
- [ ] Published win rate, expectancy, profit factor, maximum drawdown, slippage and rejected-entry rate
- [ ] Out-of-sample review, including losing periods and data gaps
- [ ] Zero unexplained positions and no live broker execution during validation
- [ ] Provider-authenticated forward market-data path (or explicitly accepted trust model) — see issue #9
- [ ] Persistent collector host with monitoring — see issue #11

Run `python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30` to enforce the minimum date-span and flat-position checks. A single deterministic sample is a smoke test, not Level 3 validation.

## Level 4 gates (after Level 3)

- [ ] Hardened deployment (non-ephemeral host, secrets hygiene, supervised processes)
- [ ] Operational monitoring, alerting, backup/restore drills
- [ ] Incident response notes and kill-switch drills
- [ ] Independent release review / security review
- [ ] Explicit written approval before any live adapter enablement

## Remaining engineering (not Level 3 by itself)

- Merge Track 2 durability (PR #22) after independent review: partial fills, correlated reservations, stress harness
- Forward-evidence gate + read-only collector (PRs #6 / #10) as **candidate** data until #9
- Scraper history-preserving import (issue #1)

Live trading remains locked. No performance or profit is guaranteed.
