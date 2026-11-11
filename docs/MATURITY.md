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

**Level 2 — Operational tooling** (target after green CI on this commit).

Foundation from Level 1 remains intact. Additional Level 2 work delivered:

- CI workflow switched from bare `pytest` (not installed) to zero-dependency `unittest`
- Paper broker now supports mark-to-market equity, commission + slippage model, and optional JSONL audit ledger
- Expanded unit tests for MtM, fees/slippage, ledger, partial close, risk edge cases, and concurrent risk evaluation
- Diagnose script, status API, execution gate, and safety defaults unchanged and still enforced

**Confirm Level 2 only after the GitHub Actions run on `main` is green.** Until that run is observed, treat the claim as provisional.

## Implemented foundation + Level 2 tooling

- [x] Unified paper-only configuration and environment template
- [x] Common broker contract and shared order/account models
- [x] In-memory PaperBroker with simulated fills, realized PnL, **MtM equity**, **fees/slippage**, **audit ledger**
- [x] Central risk gate with hard limits and default-engaged kill switch
- [x] Execution service that checks risk before submitting to a broker
- [x] Localhost-only read-only status endpoints
- [x] Unit tests (config, risk, paper, execution, status, main CLI) + concurrency smoke
- [x] CI workflow (unittest + `main.py --check` + report assert + diagnose)
- [x] Single `main.py` entry point with configuration check and status server
- [x] Local diagnostic script (`python scripts/diagnose.py`)

## Remaining before solid Level 2 confirmation

- [ ] Observe a successful GitHub Actions run on the current default branch
- [ ] Run `python scripts/diagnose.py` on a clean Python 3.11 environment (local or CI)

## Path to Level 3

- [ ] Sustained paper trading over a meaningful period with timestamped logs
- [ ] Signal quality metrics measured against a defined baseline
- [ ] Drawdown, slippage, fees, rejected orders, and execution failures recorded
- [ ] Risk rules proven under paper conditions; no unverified profit claims
- [ ] Persistent paper ledger used in real multi-day sessions

## Path to Level 4

- [ ] Production-grade deployment and secret management
- [ ] Monitoring, alerting, backups, incident response and recovery
- [ ] Independent security review and dependency scanning
- [ ] Explicit human approval process for any future live-mode unlock
- [ ] Broker-specific reconciliation and operational controls

No repository on this account is being represented as Level 4. Live trading remains locked.
