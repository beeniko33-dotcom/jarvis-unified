# START HERE — Jarvis Unified

## Current phase

**Level 2 foundation confirmed on main; Level 3 measurement work is in progress on `level-3-paper-validation`.** Do not describe the system as Level 3 until the sustained evidence gates in `docs/MATURITY.md` are met.

## Run locally

Requires Python 3.11+; runtime dependencies are standard-library only.

```bash
python main.py --check
python -m unittest discover -s tests -v
python scripts/diagnose.py
python main.py --report
python main.py --serve
# Open apps/dashboard/index.html in a browser
```

## Controlled paper validation

```bash
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30
```

The explicit `--allow-entries` flag releases only the in-memory paper risk gate for that one run. It does not alter configuration, connect to a broker, or enable real-money orders. Use append-only ledgers and archive each experiment. The report is descriptive; it does not prove signal quality or profitability.

## Source history migration

```bash
bash scripts/import_sources.sh
```

Run this on a clean local clone with Git and SSH configured. Inventory every imported source and run regression checks before porting functionality. Original source repositories must remain unchanged.

## Safety

- Paper mode only; kill switch engaged by default.
- Status API is localhost-only and read-only.
- Deriv and MT5 adapters are intentionally disabled.
- No live execution path exists.

See `docs/LEVEL_3_RUNBOOK.md`, `docs/MATURITY.md`, `docs/RISK.md` and `docs/SCRAPER.md`.
