# START HERE — Jarvis Unified

Welcome. This is the single consolidated repository.

## What just happened

All seven previous Jarvis-related repositories have been inventoried and a new clean monorepo (`jarvis-unified`) has been created as the future home.

The old repositories remain intact and will stay available for reference and history.

## Immediate priorities

1. **Secrets**
   - Rotate any previously exposed Telegram / MT5 / Deriv tokens.
   - Never commit real credentials.

2. **Foundation (Level 1 → 2)**
   - Unified configuration
   - Paper broker
   - Central risk engine
   - Status API

3. **Paper trading first**
   - Live mode stays locked until you have real measured results.

## Key documents

- `README.md` — overview and principles
- `docs/MATURITY.md` — honest maturity tracking
- `docs/ARCHITECTURE.md` — system design (coming next)
- `docs/MIGRATION.md` — source of each component
- `docs/RISK.md` — risk rules
- `docs/SCRAPER.md` — how the independent scraper lives inside the monorepo

## How to contribute during migration

Work happens in small, reviewable steps. Every major capability is brought over deliberately rather than bulk-copied.

Current phase: **Foundation**.
