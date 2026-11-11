# Jarvis Unified

**Single source of truth** for the entire Jarvis trading ecosystem.

This repository consolidates:

- `jarvis-trader-ecosystem` → core application & status infrastructure
- `jarvis-ai-trading-system` → Deriv execution engine
- `jarvis-trader` → signal logic
- `jarvistrader` → web dashboard
- `quantum-peak-pro` → research / signal concepts
- `jarvis-ai` → AI agents & memory
- `advanced-scraper` → independent data collection engine (history-preserving import pending)

## Core Principles

1. **Paper-first** — Live trading is disabled by default and requires explicit validation.
2. **Risk is king** — No strategy, AI recommendation, or signal can bypass the central risk engine.
3. **Broker-agnostic** — Strategies talk to a common interface. Deriv, MT5, Paper (and future brokers) are adapters.
4. **Preserve capability** — The full legitimate scraper feature set is a migration requirement; its original repository remains intact until the history-preserving import and regression checks are complete.
5. **No secrets in git** — All credentials live in `.env` (never committed).

## Current Status

**Maturity Level: 2 — Operational tooling (CONFIRMED)**

- Green CI on `main`
- Paper broker with mark-to-market equity, fees/slippage, and JSONL audit ledger
- Central risk gate + risk-gated execution
- Localhost-only status API + status dashboard skeleton
- SSRF-safe scraper fetch foundation
- Deriv/MT5 adapters disabled (construction raises)
- Paper session runner for Level 3 prep

See `docs/MATURITY.md` for the full maturity model and roadmap.

## Quick CLI Reference

```bash
python main.py --check
python main.py --health
python main.py --summary
python main.py --report
python main.py --serve --host localhost --port 8787
python -m unittest discover -s tests -v
python scripts/diagnose.py
python scripts/paper_session.py --allow-entries   # Level 3 prep; still paper-only
```

Open `apps/dashboard/index.html` in a browser while the status API is running.

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/START_HERE.md` | Onboarding & current state |
| `docs/ARCHITECTURE.md` | System design |
| `docs/MATURITY.md` | Honest maturity tracking |
| `docs/MIGRATION.md` | How the seven repos were consolidated |
| `docs/RISK.md` | Risk engine rules |
| `docs/SCRAPER.md` | Independent scraper module |
| `docs/DIAGNOSTIC.md` | Audit notes |

## Safety Notice

This is experimental research software. Past claims of high accuracy must be independently verified through paper trading. Never risk capital you cannot afford to lose. Live trading remains locked until paper results are measured and reviewed.
