# Roadmap — Jarvis Unified

Updated 2026-11-15.

## Level 2 — DONE

Complete on `main`.

## Engineering readiness

| Item | Status |
|------|--------|
| Track 2 durability (#22) | Merged |
| Forward evidence + Deriv collector code (#6/#10) | Merged |
| Fail-closed provenance (#26/#27) | Merged |
| Issue #9 phase 1 trust model (#29 / #30) | Merged |
| Prototype release docs (#28) | Merged |
| Biquote unverified EURUSD candidate adapter (#37) | Merged |
| Positive real-SSLSocket transport test (#32) | Merged |
| Persistent collector session supervisor (#33) | **Merged + hardened** |
| Provider research desktop survey (#34) | Note posted — **no selection** |
| Independent provider verifier (#9) | Open — evidence credit blocked |
| Persistent host provisioning (#11) | Open — no host deployed |
| Provenance policy-exception proposal (#9) | **Proposed — awaiting owner decision** — `docs/PROVENANCE_POLICY_EXCEPTION_PROPOSAL.md` |
| Streak definition vs weekly market closure | **Proposed — awaiting owner decision** — `docs/LEVEL_3_TRADING_CALENDAR_PROPOSAL.md` |
| Pilot run (operations readiness, no evidence credit) | **Proposed** — `docs/LEVEL_3_PILOT_RUN_PLAN.md` |

## Immediate sequence

1. CI confirmation of supervisor + transport tests on `main`.
2. Owner decision on whether to authorize non-binding vendor inquiries (Issue #34 → #9).
3. Provision persistent host (**#11**) only after reviewer acceptance of the operational package — see `docs/LEVEL_3_PERSISTENT_RUNNER_RUNBOOK.md`.
4. Continuous **candidate** collection + paper sessions. Unverified observations never start the 30-day clock.
5. Decide the streak definition. **Open finding (2026-11-15):** the gate counts consecutive calendar UTC days with a verified observation and has no market-closure calendar, so 30 days is unreachable for EURUSD spot (best case 6 days, Sunday to Friday). See `docs/LEVEL_3_TRADING_CALENDAR_PROPOSAL.md`. This lengthens the calendar time to certification; it cannot shorten it.
6. Only after #9 acceptance, the streak decision and first authenticated observation: start verified streak toward Level 3 (**0 / 30** today).

## Level 3 / 4

**Level 3:** not certified.  
**Level 4:** not started and **blocked** until Level 3 is certified.  
Live trading locked. No performance claims.
