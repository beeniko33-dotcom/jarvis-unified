# START HERE — Jarvis Unified

Welcome. This is the single consolidated repository.

## Current phase

**Level 2 — Operational tooling — CONFIRMED** (green CI on `main`).

Next focus: Level 3 paper validation and optional history-preserving source imports.

## Run locally

Requires Python 3.11+; no runtime third-party dependencies.

```bash
cp .env.example .env   # optional
python main.py --check
python -m unittest discover -s tests -v
python scripts/diagnose.py
python main.py --serve
# Open apps/dashboard/index.html in a browser
```

Paper session (still paper-only; requires explicit flag to allow entries):

```bash
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
```

## History import (optional, local Git + SSH)

```bash
bash scripts/import_sources.sh
# Then inventory sources/* before selective migration
```

## Safety

Kill switch engaged by default. Status API is localhost-only and read-only. Deriv/MT5 adapters cannot be constructed. No live execution path exists.

## Key documents

- `README.md` — overview
- `docs/MATURITY.md` — maturity tracking
- `docs/ARCHITECTURE.md` — design
- `docs/MIGRATION.md` — source map
- `docs/RISK.md` — risk rules
- `docs/SCRAPER.md` — scraper plan
