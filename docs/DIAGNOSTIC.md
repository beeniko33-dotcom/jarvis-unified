# Diagnostic Report — Jarvis Unified

**Date:** 2026-11-11  
**Scope:** Live repository inspection + Level 2 hardening of `beeniko33-dotcom/jarvis-unified`  
**Claimed maturity:** Level 2 — Operational tooling (provisional until green CI observed)

## Executive summary

The monorepo has a coherent paper-first foundation plus the operational tooling required for Level 2:

- Models, paper broker (now with MtM equity, fees/slippage, optional JSONL ledger), central risk gate, execution service, localhost status API, configuration hardening, unit tests, and a fixed CI workflow.
- Safety defaults remain correct (paper only, kill switch engaged, localhost-only status bind).
- CI previously called bare `pytest` with no install step; this was fixed to `python -m unittest discover` so the workflow is zero-dependency and matches the diagnose script.

Level 2 is **confirmed only after** a green GitHub Actions run on the current `main` is observed.

## Component status

| Component | Status | Notes |
|-----------|--------|-------|
| Config (`core/config.py`) | Pass | Rejects non-paper modes; rejects env kill-switch off; localhost-only status host |
| Models (`core/models.py`) | Pass | Broker-neutral OrderRequest/Result, Position, AccountSnapshot |
| Risk engine | Pass | Fail-closed; kill switch; notional / daily loss / open position limits; concurrency smoke test |
| Execution service | Pass | Risk before broker; exits allowed while entries halted |
| Paper broker | Pass (Level 2) | Idempotent client IDs; close PnL; MtM equity; commission + slippage; optional JSONL audit ledger |
| Status API | Pass | `/health`, `/status`, `/self-check`; 404 elsewhere; localhost bind enforced |
| `main.py` | Pass | `--check`, `--health`, `--summary`, `--report`, `--serve` |
| Unit tests | Present + expanded | config, risk, paper (incl. MtM/fees/ledger), execution, status, main CLI |
| CI workflow | Fixed | unittest + `main.py --check` + report assert + diagnose |
| Source imports | Not done | `scripts/import_sources.sh` ready; requires local Git + SSH |
| Scraper package | Placeholder | Full features await selective migration + SSRF hardening |
| Deriv / MT5 adapters | Disabled | Correct for this maturity |

## Safety verification (static)

- `JARVIS_MODE` other than `paper` raises at config load
- `KILL_SWITCH=false` via environment is rejected
- Status API refuses non-localhost bind
- Risk kill switch blocks new entries by default
- Risk-reducing closes remain available while entries are halted
- No live broker credentials required or activated

## Level 2 checklist

1. [x] Fix CI so tests actually run (unittest, zero deps)
2. [x] Paper broker mark-to-market equity
3. [x] Fees / slippage model
4. [x] Persistent trade/audit ledger (JSONL, optional path)
5. [x] Risk edge cases + concurrent evaluation smoke
6. [ ] Observe successful GitHub Actions run on `main`
7. [ ] Local or CI `python scripts/diagnose.py` green

## Gaps before deeper integration

1. History-preserving import of the seven source repos (`bash scripts/import_sources.sh`)
2. Inventory each `sources/<repo>` tree
3. Selective module migration (not bulk overwrite of `core/`)
4. Scraper SSRF protections before exposing URL fetch endpoints
5. Dashboard / Telegram / MCP only after sustained paper validation

## Ordered next steps

### A. Confirm CI (required for Level 2)

- Ensure Actions is enabled for the private repo
- Push (or re-run) the latest `main` workflow and confirm it is green
- Only then treat maturity as solidly Level 2

### B. Local verify

```bash
git clone git@github.com:beeniko33-dotcom/jarvis-unified.git
cd jarvis-unified
python -m venv .venv && source .venv/bin/activate
python -m unittest discover -s tests -v
python scripts/diagnose.py
python main.py --check
python main.py --report
```

### C. After green CI + local diagnose

1. Inventory `sources/*` after history import
2. Use the paper ledger in multi-day sessions
3. Port scraper as independent package with SSRF controls
4. Dashboard status-only UI against the existing status API
5. Deriv demo adapter behind the same risk gate (still non-live)

## Open tracking issues

- [#1 Complete history-preserving migration](https://github.com/beeniko33-dotcom/jarvis-unified/issues/1)
- [#2 Verify Level 2 CI and harden paper runtime](https://github.com/beeniko33-dotcom/jarvis-unified/issues/2)

## Source PR posture (unchanged)

- Merged: `jarvis-trader-ecosystem` #1 (Telegram access control)
- Draft / leave open: signal RSI, Deriv CI, jarvistrader env cleanup, jarvis-ai CI repair, scraper API (SSRF blocker)
- No original repositories deleted or archived
