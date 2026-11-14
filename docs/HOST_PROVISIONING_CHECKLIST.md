# Persistent host provisioning checklist — Issue #11

**Status:** checklist only. No cloud account, VM, or collector process is created by this document.

Pairs with `docs/LEVEL_3_PERSISTENT_RUNNER_RUNBOOK.md` and the Issue #9 trust model. Market-data on this host remains **candidate** evidence until provenance policy is accepted.

## 1. Provider preference

| Preference | Notes |
|------------|--------|
| **1. Oracle Cloud Always Free** | Ampere A1 or small x86 free tier; persistent block volume |
| **2. Google Cloud free tier / e2-micro** | Confirm current free eligibility; prefer persistent disk |
| Avoid | GitHub Actions, Cloud Shell only, spot without persistent volume |

## 2. Oracle Cloud (outline)

Operator performs these steps in the Oracle console / CLI (not automated here):

1. Create / select a **Always Free** compute instance (Ubuntu 22.04+ or Oracle Linux).
2. Attach **block volume**; mount under e.g. `/var/lib/jarvis` (XFS/ext4).
3. Open **egress only** as needed for DNS + `api.derivws.com:443`; no public inbound for the collector.
4. Create unprivileged user `jarvis-collector`.
5. Install CPython 3.11.18, clone the repo at a **reviewed commit**, create a venv, then install `python -m pip install "pip==26.3" -r requirements-market-data.lock`. The full CI/test dependency set is `requirements-lock.txt`; do not install test tooling on the production collector unless needed.
6. Enable **chrony** or systemd-timesyncd; document NTP sources.
7. Install systemd unit from the persistent runner runbook (adapt paths).
8. Restrict file modes on DB directory (`0700`).
9. Schedule **daily backup** of SQLite (online backup API or consistent snapshot) to a second path or object storage.
10. Run **restore drill** once before claiming ops readiness.

## 3. Smoke tests on host (after provision)

```bash
# Paper foundation (no market-data required)
python scripts/diagnose.py
python main.py --check

# Short read-only collect (candidate evidence only)
python -m research.deriv_feed --duration-seconds 120 --db /var/lib/jarvis/deriv_eurusd_forward.sqlite3
```

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
