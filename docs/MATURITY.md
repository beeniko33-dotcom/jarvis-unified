# Maturity Model — Jarvis Unified

Honest tracking only. No marketing claims.

## Levels

| Level | Name | Meaning |
|-------|------|--------|
| **0** | Skeleton | Placeholder / incomplete ideas |
| **1** | Foundation | Clean structure, secrets hygiene, single config, runnable entry point |
| **2** | Operational tooling | Status API, CI smoke tests, config checks, dashboard skeleton, paper broker working |
| **3** | Paper-validated | You have measured real signal quality over a meaningful period (weeks) with logged results |
| **4** | Production | Hardened deploy, monitoring, real risk controls enforced, no exposed defaults, live trading allowed under strict limits |

## Current Status (November 2026)

**Level 1 — Foundation** (just started)

- New monorepo created
- Core principles documented
- Target architecture defined
- All source repositories preserved

## Path to Level 2

- [ ] Unified configuration + `.env.example`
- [ ] Paper broker fully functional
- [ ] Central risk engine (hard limits, kill switch)
- [ ] Status API (`/health`, `/status`)
- [ ] Basic tests + CI
- [ ] Single `main.py` entry point with mode selection

## Path to Level 3

- [ ] Sustained paper trading with honest logging
- [ ] Signal quality metrics measured by you (not claimed)
- [ ] Risk rules proven under paper conditions

## Path to Level 4

- [ ] Production-grade Docker / systemd deployment
- [ ] Monitoring + alerting
- [ ] Live credentials isolated and rotated
- [ ] Explicit human approval process for enabling live mode

No repository on this account has ever reached Level 4. That remains the goal, not the starting point.
