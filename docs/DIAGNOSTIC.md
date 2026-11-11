# Diagnostic Report — Jarvis Unified

**Date:** 2026-11-11  
**Claimed maturity:** **Level 2 — Operational tooling (CONFIRMED)**

## Evidence

- GitHub Actions workflow `CI` active on `main`
- Successful runs after CI YAML hardening (e.g. run #62, #63)
- Jobs execute: unittest, `main.py --check`, report assert, `scripts/diagnose.py`

## Component status

| Component | Status |
|-----------|--------|
| Config / kill switch / paper-only | Pass |
| Risk + ExecutionService | Pass |
| Paper broker (MtM, fees, ledger) | Pass |
| Status API + dashboard skeleton | Pass |
| Portfolio + SignalIntent | Pass |
| SSRF-safe fetch | Pass (reject tests) |
| Deriv/MT5 | Disabled (raise on construct) |
| Source history import | Not done (local Git required) |
| Live trading | Locked |

## Operator next steps

1. Keep running paper sessions; store ledgers under `var/`
2. When ready: `bash scripts/import_sources.sh` on a clean clone with SSH access
3. Inventory `sources/*` before any selective port
4. Do not enable live adapters without Level 3 measured results and explicit approval
