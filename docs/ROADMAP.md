# Roadmap — Jarvis Unified

Honest path after 2026-11-13 merges on `main`.

## Level 2 — DONE

Complete. Issues #2 and #8 closed. Track 2 durability is **merged** (PR #22).

## Engineering readiness — largely merged (still not Level 3)

| Item | Status |
|------|--------|
| PR #22 Track 2 durability | **Merged** · main CI green |
| PR #6 forward-evidence gate | **Merged** · candidates only |
| PR #10 read-only Deriv collector | **Merged** · code only, not hosted |
| PR #25–#27 fail-closed provenance | **Merged** |
| PR #28 prototype release docs | **Merged** |

## Paper prototype (now)

```bash
python scripts/diagnose.py
python main.py --check
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --min-days 1
```

Follow `docs` prototype release track: paper-only, kill switch on, no live credentials.

## Level 3 — remaining sequence

1. **Issue #9** — implement and independently review a real provider trust verifier (no injectable callbacks).
2. **Issue #11** — provision persistent host (Oracle Cloud or alternative), supervision, UTC sync, monitoring, backup/restore drill.
3. Start **genuine** forward collection; observations stay candidates until #9 accepts them.
4. Run **30 consecutive UTC days** of paper validation with full metrics (issue #3).
5. Independent review of the evidence package.

Verified forward days today: **0 / 30**.

## Level 4 — design only until Level 3

Monitoring, DR, access control, incident response, independent release approval, written auth before any live path.

## What not to do

- Do not treat merge of collector code as “collector deployed.”
- Do not award Level 3 from synthetic 1,000-cycle stress.
- Do not enable live trading without Level 3 + Level 4 gates + written authorization.
