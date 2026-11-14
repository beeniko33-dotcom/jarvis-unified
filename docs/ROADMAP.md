# Roadmap — Jarvis Unified

Updated 2026-11-14 (later).

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
| Persistent collector session supervisor (#33) | **Merged + hardened** (stale lock, backoff, signals, health) |
| Independent provider verifier (#9) | Open — evidence credit blocked |
| Persistent host provisioning (#11) | Open — no host deployed |

## Immediate sequence

1. CI confirmation of supervisor + transport tests on `main`.
2. Owner / independent review of any future evidence-credit path (Issue #9). Current gate remains `BLOCKED_PROVENANCE`.
3. Provision persistent host (**#11**) only after reviewer acceptance of the operational package — see `docs/LEVEL_3_PERSISTENT_RUNNER_RUNBOOK.md`.
4. Continuous **candidate** collection + paper sessions. Unverified observations never start the 30-day clock.
5. Only after #9 acceptance and first authenticated observation: start verified streak toward Level 3 (**0 / 30** today).

## Level 3 / 4

Not certified. Live trading locked. No performance claims.
