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

## How to contribute during migration

Work happens in small, reviewable steps. Every major capability is brought over deliberately rather than bulk-copied.

Current phase: **Level 1 foundation implementation; Level 2 validation pending**.
