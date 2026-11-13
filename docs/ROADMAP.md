# Roadmap — finish Level 2, pursue Level 3/4, ship a paper prototype

This is the honest path. Skipping gates is not finishing.

## Level 2 — DONE on `main`

**Status: complete.** Issues #2 and #8 closed against current `main`.

You already have: CI, paper broker, risk gate, kill switch, status API, persistent ledger/UTC risk, disabled live adapters.

**Optional polish (does not change Level 2 status):**
1. Independent review + merge of PR **#22** (Track 2 durability + 1k synthetic stress).
2. Keep `python scripts/diagnose.py` green on every main push.

---

## Paper prototype (what you can run *now*)

A prototype means a **local paper system**, not live trading and not Level 3.

```bash
# Sanity
python scripts/diagnose.py
python main.py --check

# One paper session + report (smoke)
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --min-days 1

# Toward Level 3 measurement (still not certification until 30 real days + review)
# Run daily; append to the same ledger; never delete history.
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30
```

Prototype boundaries:

- Kill switch stays engaged for production configs.
- Deriv/MT5 adapters stay construction-blocked.
- No wallet, no account tokens, no order endpoints.
- Synthetic 1,000-cycle stress ≠ 30 calendar days of evidence.

---

## Level 3 — cannot be closed by code alone

**Minimum calendar work: ~30 consecutive UTC days** of real append-only paper evidence, plus review.

| Step | Action | Issue / PR |
|------|--------|------------|
| 1 | Merge Track 2 after review | PR #22 |
| 2 | Land evidence store (candidates only) | PR #6 |
| 3 | Land read-only collector (still candidates) | PR #10 |
| 4 | Provider verifier or accepted trust model | **#9** |
| 5 | Persistent host + monitoring + backup drill | **#11** |
| 6 | Run paper sessions **every day**; keep ledgers | Issue **#3** |
| 7 | Publish metrics; out-of-sample review; independent sign-off | Issue **#3** |

Until steps 4–7 are true, the answer to “are we Level 3?” is **no**.

---

## Level 4 — after Level 3

Only after Level 3 evidence exists:

1. Production host hardening (not CI runners).
2. Monitoring, alerting, backup/restore, incident notes.
3. Independent security / release review.
4. Written approval before any live path is unlocked.

There is no shortcut that jumps from Level 2 CI to Level 4.

---

## Issue triage (2026-11-13)

| Issue | Disposition |
|-------|-------------|
| **#2** Level 2 CI / paper runtime | **Closed — completed** |
| **#8** Restart-safe paper + UTC risk | **Closed — completed** (main has PR #12) |
| **#3** Level 3 sustained validation | Open — needs 30-day evidence |
| **#9** Provider verifier | Open — blocks verified forward days |
| **#11** Persistent collector host | Open — ops, not CI |
| **#1** Source history import | Open — separate migration track |

---

## What “fix all issues” cannot mean

Closing #3 / #9 / #11 without a host, a verifier, and 30 days of ledgers would be false certification. This project’s rule is honest maturity tracking.
