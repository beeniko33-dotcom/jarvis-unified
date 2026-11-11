# START HERE — Jarvis Unified

Welcome. This is the single consolidated repository.

## What just happened

All seven previous Jarvis-related repositories have been inventoried and a new clean monorepo (`jarvis-unified`) has been created as the future home.

The old repositories remain intact and will stay available for reference and history.

## Current phase

**Level 2 — Operational tooling** (provisional until a green GitHub Actions run on `main` is observed).

- Paper broker supports mark-to-market equity, commission/slippage, and optional JSONL audit ledger
- Central risk engine + execution gate
- Localhost-only status API
- Zero-dependency unit tests and CI
- `python scripts/diagnose.py` for local validation

## Immediate priorities

1. **Secrets**
   - Rotate any previously exposed Telegram / MT5 / Deriv tokens.
   - Never commit real credentials.

2. **Confirm Level 2**
   - Ensure Actions is enabled and the latest `main` workflow is green.
   - Run `python scripts/diagnose.py` locally on Python 3.11+.

3. **Paper trading first**
   - Live mode stays locked until you have real measured results.

## Run the current foundation

Requires Python 3.11+; there are no runtime third-party dependencies.

```bash
# Optional: copy the template and load it into the current shell
cp .env.example .env
set -a && . ./.env && set +a

# Validate configuration and initialize the paper runtime
python main.py --check

# Run the test suite
python -m unittest discover -s tests -v

# Local diagnostic
python scripts/diagnose.py

# Start the read-only local status API
python main.py --serve
# In another terminal: curl http://127.0.0.1:8787/health
# or: curl http://127.0.0.1:8787/status
```

The kill switch is engaged by default. The status API does not expose an order-placement endpoint. No Deriv, MT5, or live execution adapter is enabled.

## Key documents

- `README.md` — overview and principles
- `docs/MATURITY.md` — honest maturity tracking
- `docs/ARCHITECTURE.md` — system design
- `docs/MIGRATION.md` — source of each component
- `docs/RISK.md` — risk rules
- `docs/SCRAPER.md` — how the independent scraper lives inside the monorepo
- `docs/DIAGNOSTIC.md` — latest audit notes

## How to contribute during migration

Work happens in small, reviewable steps. Every major capability is brought over deliberately rather than bulk-copied.

Current phase: **Level 2 operational tooling; green CI confirmation pending**.
