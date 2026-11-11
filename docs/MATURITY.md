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

**Level 2 — Operational tooling — CONFIRMED**

Green GitHub Actions runs observed on `main` (e.g. workflow runs #62 and #63 after the CI YAML fix). Unit tests, `main.py --check`, report payload assertions, and `scripts/diagnose.py` execute in CI.

### Delivered

- Paper-only config; kill switch engaged by default (not env-overridable)
- Central risk gate + ExecutionService
- Paper broker: fills, realized PnL, MtM equity, fees/slippage, JSONL audit ledger
- Localhost status API + static status dashboard
- Portfolio tracker + SignalIntent contract
- Deriv/MT5 adapters present but construction raises (cannot be used)
- SSRF-safe fetch foundation (`packages/scraper/safe_fetch.py`)
- Paper session runner for Level 3 prep
- Zero-dependency unittest CI with `workflow_dispatch`

## Level 3 path (next)

- [ ] Run sustained paper sessions with `scripts/paper_session.py --allow-entries` and retain ledgers under `var/`
- [ ] Define signal quality baseline metrics (win rate, expectancy, max drawdown, rejection rate)
- [ ] Multi-day timestamped logs; no profit claims without measured data
- [ ] Optional: import source histories via `bash scripts/import_sources.sh` (local Git + SSH required)
- [ ] Selective strategy migration only after inventory of `sources/*`

## Level 4 path (later)

- Production deployment, secrets, monitoring, incident response
- Independent security review
- Human approval gate for any live-mode unlock
- Broker reconciliation

Live trading remains locked.
