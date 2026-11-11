# Maturity Model — Jarvis Unified

Honest tracking only. No marketing claims.

## Levels

| Level | Name | Meaning |
|-------|------|--------|
| **0** | Skeleton | Placeholder / incomplete ideas |
| **1** | Foundation | Clean structure, secrets hygiene, single config, runnable entry point |
| **2** | Operational tooling | Status API, passing CI, config checks, working paper broker and risk-gated execution |
| **3** | Paper-validated | Sustained paper trading with measured signal quality and auditable results |
| **4** | Production | Hardened deployment, monitoring, operational risk controls, formal approvals and independently reviewed release gates |

## Current status — November 2026

**Level 1 — Foundation implementation in progress.** The repository now contains the initial broker-neutral models, in-memory paper broker, common broker contract, central risk engine, execution gate, localhost read-only status API, paper-only configuration, entry point, unit tests, and a GitHub Actions workflow.

This is not yet Level 2: GitHub has not returned a passing CI status for the current commits, the tests have not yet been independently observed passing in Actions, and several production-critical behaviors remain unimplemented.

## Implemented foundation

- [x] Unified paper-only configuration and environment template
- [x] Common broker contract and shared order/account models
- [x] In-memory PaperBroker with simulated fills and realized PnL
- [x] Central risk gate with hard limits and default-engaged kill switch
- [x] Execution service that checks risk before submitting to a broker
- [x] Localhost-only read-only status endpoints
- [x] Basic unit tests and CI workflow definition
- [x] Single `main.py` entry point with configuration check and status server

## Remaining before Level 2

- [ ] Observe a successful GitHub Actions run on the current default branch
- [ ] Run and verify the test suite on a clean environment
- [ ] Add status API integration tests and operational error handling
- [ ] Add paper broker valuation, fees/slippage model, and persistent trade/audit ledger
- [ ] Add safe dashboard status skeleton
- [ ] Review risk edge cases, order reconciliation, and concurrent execution

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
