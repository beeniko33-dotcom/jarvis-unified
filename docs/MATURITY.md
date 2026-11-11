# Maturity Model — Jarvis Unified

Honest tracking only. No marketing claims.

## Levels

| Level | Name | Meaning |
|-------|------|--------|
| **0** | Skeleton | Placeholder / incomplete ideas |
| **1** | Foundation | Clean structure, secrets hygiene, single config, runnable entry point |
| **2** | Operational tooling | Status API, **passing CI**, config checks, working paper broker and risk-gated execution |
| **3** | Paper-validated | Sustained paper trading with measured signal quality and auditable results |
| **4** | Production | Hardened deployment, monitoring, operational risk controls, formal approvals and independently reviewed release gates |

## Current status — November 2026

**Level 1 — Foundation.** Models, in-memory paper broker, risk gate, execution service, localhost status API, paper-only config, tests, CI workflow, and `scripts/diagnose.py` are present.

This is **not** Level 2 until a green GitHub Actions run on `main` is observed. See `docs/DIAGNOSTIC.md` for the full audit.

## Implemented foundation

- [x] Unified paper-only configuration and environment template
- [x] Common broker contract and shared order/account models
- [x] In-memory PaperBroker with simulated fills and realized PnL
- [x] Central risk gate with hard limits and default-engaged kill switch
- [x] Execution service that checks risk before submitting to a broker
- [x] Localhost-only read-only status endpoints
- [x] Unit tests (config, risk, paper, execution, status)
- [x] CI workflow (unittest + `main.py --check` + diagnose)
- [x] Single `main.py` entry point with configuration check and status server
- [x] Local diagnostic script (`python scripts/diagnose.py`)

## Remaining before Level 2

- [ ] Observe a successful GitHub Actions run on the current default branch
- [ ] Run `python scripts/diagnose.py` on a clean Python 3.11 environment
- [ ] Paper broker mark-to-market equity, fees/slippage model, persistent trade/audit ledger
- [ ] Risk edge cases, order reconciliation, concurrent execution review
- [ ] Safe dashboard status skeleton (optional for Level 2 minimum)

## Path to Level 3

- [ ] Sustained paper trading over a meaningful period with timestamped logs
- [ ] Signal quality metrics measured against a defined baseline
- [ ] Drawdown, slippage, fees, rejected orders, and execution failures recorded
- [ ] Risk rules proven under paper conditions; no unverified profit claims

## Path to Level 4

- [ ] Production-grade deployment and secret management
- [ ] Monitoring, alerting, backups, incident response and recovery
- [ ] Independent security review and dependency scanning
- [ ] Explicit human approval process for any future live-mode unlock
- [ ] Broker-specific reconciliation and operational controls

No repository on this account is being represented as Level 4. Live trading remains locked.
