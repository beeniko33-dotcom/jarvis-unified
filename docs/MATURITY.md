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

As of 2026-11-13, `main` also includes Track 2 paper durability, forward-evidence storage, read-only Deriv collector code, fail-closed provenance hardening, and paper-prototype release documentation (merged PRs #22, #6, #10, #25–#28 and related).

**Level 3 is not certified.** Merged code does **not** equal verified forward days. Synthetic stress, historical replay, and CI fixtures do **not** count as Level 3 evidence. Unverified observations remain candidates only (BLOCKED_PROVENANCE until issue #9).

**Level 4 is not started** as a certification target.

## Delivered on main (Level 2 + engineering readiness)

- Paper-only config; kill switch engaged by default and not env-overridable
- Central risk gate + ExecutionService
- Paper broker with fills, realized PnL, mark-to-market equity, fees/slippage and JSONL audit ledger
- Restart-safe persistent paper ledger (SQLite WAL, hash-chained events, UTC-day accounting)
- Partial fills, crash recovery, correlated exposure reservations (Track 2)
- Peak-equity drawdown and per-symbol / correlated exposure controls
- Forward-evidence store (candidates only; fail-closed against injectable verifiers)
- Read-only Deriv EURUSD collector **code** (no host deployment claimed)
- Fail-closed TLS claim handling (no caller-supplied verified transport)
- Localhost read-only status API and dashboard
- Paper session runner, analytics report, foundation diagnostic
- Paper-only prototype release documentation (PR #28)

## Level 3 evidence gates (all required)

- [ ] At least 30 consecutive calendar days of timestamped paper ledgers
- [ ] Signal-level attribution: strategy/version, data source, signal, entry/exit and rationale
- [ ] Reconciliation of fills, fees, PnL and all open positions
- [ ] Published win rate, expectancy, profit factor, maximum drawdown, slippage and rejected-entry rate
- [ ] Out-of-sample review, including losing periods and data gaps
- [ ] Zero unexplained positions and no live broker execution during validation
- [ ] Provider-authenticated forward market-data path (or explicitly accepted trust model) — **issue #9**
- [ ] Persistent collector host with monitoring — **issue #11**

Run `python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30` for date-span checks. A smoke session is not Level 3 validation.

## Level 4 gates (after Level 3)

- [ ] Hardened deployment (non-ephemeral host, secrets hygiene, supervised processes)
- [ ] Operational monitoring, alerting, backup/restore drills
- [ ] Incident response notes and kill-switch drills
- [ ] Independent release review / security review
- [ ] Explicit written approval before any live adapter enablement

## Remaining (honest)

- **#9** — real provider-specific verifier (or accepted trust model) before evidence credit
- **#11** — provision persistent host; runbooks alone are not deployment
- **#3** — 30 genuine forward-validation days + review
- **#1** — history-preserving source import (separate track)

Live trading remains locked. No performance or profit is guaranteed.
