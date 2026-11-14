# Persistent host provisioning checklist — Issue #11

**Status:** checklist only. No cloud account, VM, or collector process is created by this document. The Deriv parser now recognizes the current catalog response; a successful subscription check at market open and provenance review are still required.

Pairs with `docs/LEVEL_3_PERSISTENT_RUNNER_RUNBOOK.md` and the Issue #9 trust model. Market-data on this host remains **candidate** evidence until provenance policy is accepted.

## 1. Provider preference

The host provider below is separate from the market-data provider. The market-data source and instrument must be confirmed before enabling a persistent collector.

| Preference | Notes |
|------------|--------|
| **1. Oracle Cloud Always Free** | Ampere A1 or small x86 free tier; persistent block volume |
| **2. Google Cloud free tier / e2-micro** | Confirm current free eligibility; prefer persistent disk |
| Avoid | GitHub Actions, Cloud Shell only, spot without persistent volume |

## 2. Oracle Cloud (outline)

Operator performs these steps in the Oracle console / CLI (not automated here):

1. Create / select a **Always Free** compute instance (Ubuntu 22.04+ or Oracle Linux).
2. Attach **block volume**; mount under e.g. `/var/lib/jarvis` (XFS/ext4).
3. Open **egress only** for DNS and the selected provider's documented endpoint on port 443; no public inbound for the collector.
4. Create unprivileged user `jarvis-collector`.
5. Install CPython 3.11.18, clone the repo at a **reviewed commit**, create a venv, then install `python -m pip install "pip==26.3" -r requirements-market-data.lock`. The full CI/test dependency set is `requirements-lock.txt`; do not install test tooling on the production collector unless needed.
6. Enable **chrony** or systemd-timesyncd; document NTP sources.
7. Install systemd unit from the persistent runner runbook (adapt paths).
8. Restrict file modes on DB directory (`0700`).
9. Schedule **daily backup** of SQLite (online backup API or consistent snapshot) to a second path or object storage.
10. Run **restore drill** once before claiming ops readiness.

## 3. Smoke tests on host (after provider selection and provision)

```bash
# Paper foundation (no market-data required)
python scripts/diagnose.py
python main.py --check

# Deriv only: run after its public catalog advertises canonical FRXEURUSD.
python -m research.deriv_feed --duration-seconds 120 --db /var/lib/jarvis/deriv_eurusd_forward.sqlite3
```

As of 2026-11-14, the read-only Deriv catalog returned 95 active symbols and included EUR/USD as `underlying_symbol=frxEURUSD`. The parser now accepts both the legacy and current field names. A read-only subscription attempt returned `MarketIsClosed` and the provider response stated the market would reopen at `2026-11-16 00:00:00`; repeat the subscription smoke test after reopening before scheduling a collector or provisioning a 30-day run. Public tick provenance remains unverified, so this does not remove the Issue #9 gate.

Confirm:

- Process exits cleanly or is supervised
- Report shows `level_3_certification: false`
- Gate is `BLOCKED_PROVENANCE` or equivalent (0 verified)
- `websocket` exposes TLS socket compatible with PR #30 session builder (if #30 merged)

## 4. Acceptance vs Level 3

| Milestone | Counts as |
|-----------|-----------|
| VM up + systemd + backup drill | Issue **#11** progress |
| Continuous candidate ticks | Ops readiness |
| Verified 30-day streak | Only after Issue **#9** policy + verifier acceptance |

## 5. Explicit non-actions

- No live trading credentials on this host
- No kill-switch release
- No rewriting missing UTC days
- No claiming Level 3 from uptime alone
