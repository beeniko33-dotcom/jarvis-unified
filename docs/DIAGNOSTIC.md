# Diagnostic Report — Jarvis Unified

**Date:** 2026-11-11  
**Scope:** Live repository inspection of `beeniko33-dotcom/jarvis-unified`  
**Claimed maturity:** Level 1 (Foundation) — **not** Level 2

## Executive summary

The monorepo has a coherent paper-first foundation: models, paper broker, central risk gate, execution service, localhost status API, configuration hardening, unit tests, and a CI workflow definition. Safety defaults are correct (paper only, kill switch engaged, localhost-only status bind).

Level 2 is **not** verified: no confirmed green GitHub Actions run was observed for the current default branch, and source histories have not yet been imported.

## Component status

| Component | Status | Notes |
|-----------|--------|-------|
| Config (`core/config.py`) | Pass | Rejects non-paper modes; rejects env kill-switch off; localhost-only status host |
| Models (`core/models.py`) | Pass | Broker-neutral OrderRequest/Result, Position, AccountSnapshot |
| Risk engine | Pass | Fail-closed; kill switch; notional / daily loss / open position limits |
| Execution service | Pass | Risk before broker; exits allowed while entries halted |
| Paper broker | Pass (in-memory) | Idempotent client IDs; close PnL; rejects bad/non-finite values |
| Status API | Pass | `/health`, `/status`; 404 elsewhere; localhost bind enforced |
| `main.py` | Pass | `--check`, `--serve` |
| Unit tests | Present | config, risk, paper, execution, status |
| CI workflow | Defined | unittest + `main.py --check` on push/PR to main |
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

## Gaps before Level 2

1. Observe a successful Actions run on `main`
2. Run `python scripts/diagnose.py` on a clean Python 3.11 environment
3. Paper ledger persistence (audit trail)
4. Mark-to-market equity + optional fees/slippage model
5. Stronger concurrency / partial-close edge-case coverage

## Gaps before deeper integration

1. History-preserving import of the seven source repos (`bash scripts/import_sources.sh`)
2. Inventory each `sources/<repo>` tree
3. Selective module migration (not bulk overwrite of `core/`)
4. Scraper SSRF protections before exposing URL fetch endpoints
5. Dashboard / Telegram / MCP only after risk + paper ledger are solid

## Ordered next steps

### A. Local (you / Codespace)

```bash
git clone git@github.com:beeniko33-dotcom/jarvis-unified.git
cd jarvis-unified
python -m venv .venv && source .venv/bin/activate
python scripts/diagnose.py
# After green local diagnose:
bash scripts/import_sources.sh
git push origin main
```

### B. CI gate

- Confirm Actions is enabled for the private repo
- Confirm the latest `main` workflow run is green
- Only then update `docs/MATURITY.md` to Level 2

### C. After import + green CI

1. Inventory `sources/*`
2. Port persistent paper ledger
3. Port scraper as independent package with SSRF controls
4. Dashboard skeleton against status API
5. Deriv demo adapter behind the same risk gate (still non-live)

## Open tracking issues

- [#1 Complete history-preserving migration](https://github.com/beeniko33-dotcom/jarvis-unified/issues/1)
- [#2 Verify Level 2 CI and harden paper runtime](https://github.com/beeniko33-dotcom/jarvis-unified/issues/2)

## Source PR posture (unchanged)

- Merged: `jarvis-trader-ecosystem` #1 (Telegram access control)
- Draft / leave open: signal RSI, Deriv CI, jarvistrader env cleanup, jarvis-ai CI repair, scraper API (SSRF blocker)
- No original repositories deleted or archived
