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

**Maturity Level: 2 — Operational tooling** (provisional until a green GitHub Actions run on `main` is observed)

- Paper broker with mark-to-market equity, fees/slippage, and optional JSONL audit ledger
- Central risk gate + risk-gated execution
- Localhost-only status API
- Zero-dependency unit tests + CI workflow
- `python scripts/diagnose.py` for local validation

See `docs/MATURITY.md` for the full maturity model and roadmap.

## Target Structure

```
jarvis-unified/
├── apps/
│   ├── api/                 # Status + control API
│   ├── dashboard/           # Next.js web UI (from jarvistrader)
│   ├── telegram/            # Telegram bot
│   └── mobile/              # Expo + Flutter companions
├── core/
│   ├── brain/               # AI agents & decision engine
│   ├── signals/             # Signal generation
│   ├── risk/                # Central risk authority
│   ├── memory/              # Persistent + vector memory
│   └── portfolio/           # Position & PnL tracking
├── brokers/
│   ├── deriv/               # Deriv adapter (from jarvis-ai-trading-system)
│   ├── mt5/                 # MT5 adapter
│   └── paper/               # Simulated execution (default)
├── packages/
│   ├── scraper/             # Full advanced-scraper (independent)
│   ├── research/
│   ├── analytics/
│   └── shared/
├── infrastructure/
│   ├── docker/
│   ├── monitoring/
│   └── deployment/
├── tests/
├── docs/
├── .env.example
├── pyproject.toml
└── main.py
```

## Quick CLI Reference

Use the project entry point directly from the repo root:

```bash
python main.py --check
python main.py --health
python main.py --summary
python main.py --report
python main.py --serve --host localhost --port 9002
```

These commands are intentionally safe and paper-first:

- `--check` validates config and initializes the paper broker.
- `--health` returns a minimal `{"ok": true}` payload for health checks.
- `--summary` prints a compact runtime snapshot.
- `--report` exposes a single JSON payload containing version, runtime, and account data.
- `--serve` starts the localhost-only status API for operational monitoring.

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/START_HERE.md` | Onboarding & current state |
| `docs/ARCHITECTURE.md` | System design |
| `docs/MATURITY.md` | Honest maturity tracking |
| `docs/MIGRATION.md` | How the seven repos were consolidated |
| `docs/RISK.md` | Risk engine rules |
| `docs/SCRAPER.md` | Independent scraper module |

## Safety Notice

This is experimental research software. Past claims of high accuracy must be independently verified through paper trading. Never risk capital you cannot afford to lose. Live trading remains locked until paper results are measured and reviewed.
