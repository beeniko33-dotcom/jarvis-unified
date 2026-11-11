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

**Level 2 — Operational tooling** (provisional until a green GitHub Actions run is observed).

Delivered beyond the Level 1 foundation:

- CI workflow hardened (unittest, workflow_dispatch, permissions, block scalars)
- Paper broker: MtM equity, fees/slippage, JSONL audit ledger, idempotent client IDs
- Portfolio tracker, SignalIntent contract
- Deriv/MT5 adapters present but **construction raises** (cannot be used)
- SSRF-safe fetch primitive under `packages/scraper`
- Status-only dashboard HTML
- Paper session runner (`scripts/paper_session.py`) for Level 3 prep
- Expanded unit tests

**Confirm Level 2 only after the GitHub Actions run on `main` is green.**

## Checklist

### Level 2
- [x] Paper-only config + kill switch defaults
- [x] Risk-gated execution
- [x] Paper broker with MtM / fees / ledger
- [x] Localhost status API + status dashboard skeleton
- [x] Unit tests + diagnose script
- [x] CI workflow definition (verify green run)
- [ ] Observe successful Actions run on `main`

### Level 3 prep (started)
- [x] Paper session runner with audit events
- [x] SignalIntent contract (no direct broker access)
- [ ] Sustained multi-day paper logs with measured metrics
- [ ] Signal quality baseline definition

### Migration
- [ ] History-preserving import via `scripts/import_sources.sh` (requires local Git + SSH)
- [ ] Source inventory under `sources/*`
- [x] SSRF-safe fetch foundation before exposing scraper network APIs
- [x] Disabled Deriv/MT5 skeletons behind explicit unlock policy

## Path to Level 4

- Production deployment, secrets, monitoring, incident response
- Independent security review
- Human approval gate for any live-mode unlock
- Broker reconciliation

Live trading remains locked.
