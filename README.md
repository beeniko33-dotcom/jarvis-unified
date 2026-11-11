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
4. **Preserve capability** — The scraper remains a fully functional, independently configurable module.
5. **No secrets in git** — All credentials live in `.env` (never committed).

## Current Status

**Maturity Level: 1 — Foundation** (core scaffolding committed; CI validation pending)

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
