# Ops runbook — Issue #11 persistent paper-only collector

**Purpose:** Stand up a supervised, read-only market-data collector on a **persistent host**.  
**Not** Level 3 certification. **Not** live trading. **Not** CI-as-host.

Paper kill switch stays engaged. Broker adapters stay disabled. No account tokens, App IDs, wallets, or order endpoints.

---

## 1. Preconditions

- [ ] PR stack for collector path independently reviewed (`#6` → `#10` as applicable)
- [ ] Evidence gate still treats unverified ticks as **candidates** until issue #9 verifier exists
- [ ] Host has persistent disk (not ephemeral CI)
- [ ] UTC clock synchronized (chrony/systemd-timesyncd)
- [ ] Only optional `market-data` dependency installed for the collector process

## 2. Host layout (example)

```text
/var/jarvis/
  data/          # SQLite WAL + evidence DB
  backups/       # dated copies
  logs/
  run/           # pid / heartbeat files
```

Environment (illustrative):

```bash
export JARVIS_DATA_DIR=/var/jarvis/data
export JARVIS_BACKUP_DIR=/var/jarvis/backups
export JARVIS_LOG_DIR=/var/jarvis/logs
# No DERIV_TOKEN, no MT5 credentials, no wallet keys
```

## 3. Process supervision

Prefer **systemd** (or equivalent) with:

- `Restart=on-failure`
- `RestartSec=5`
- Working directory under `/var/jarvis`
- User with write access only to data/logs/backups
- No network capabilities beyond outbound WSS to the documented public Deriv endpoint

Health checks:

- Heartbeat file or HTTP localhost status (if status API is bound to localhost only)
- Feed freshness (last tick age)
- Disk free space threshold
- SQLite integrity / hash-chain verify on a schedule

## 4. Backup and restore drill

1. Stop collector cleanly (or checkpoint WAL: `PRAGMA wal_checkpoint(FULL)`).
2. Copy SQLite DB + WAL/SHM (if present) to `backups/YYYY-MM-DDTHHMMZ/`.
3. Restore to a scratch path and open read-only; verify chain / row counts.
4. Document result in the ops log. **A drill that was never run does not count.**

## 5. Alerting (minimum)

| Condition | Action |
|-----------|--------|
| Feed disconnect > N minutes | Alert |
| Stale quotes / missed UTC day | Alert |
| Hash-chain / ledger verify fail | Alert + fail closed |
| Disk < threshold | Alert |
| Clock drift beyond policy | Alert |
| Backup job failed | Alert |

## 6. First live public tick (candidate only)

Record:

- Collector git commit SHA
- Host identity
- Endpoint URL
- TLS verification outcome
- Collector receive timestamp (UTC)
- Raw payload hash

Do **not** mark the observation **verified** unless issue #9 provider verifier is installed and independently reviewed. CI fixtures and historical OHLCV replay are not forward evidence.

## 7. Explicit non-goals

- Level 3 certification from uptime alone
- Enabling order execution or releasing the kill switch
- Storing or using trading account credentials
- Running the collector on GitHub Actions runners as the permanent host

## 8. Acceptance checklist (issue #11)

- [ ] Runbook reviewed by operator
- [ ] Supervised process running on persistent disk
- [ ] Backup/restore drill completed and logged
- [ ] Monitoring and alerts wired
- [ ] First public tick recorded as **candidate** with provenance fields above
- [ ] Still zero independently **verified** forward days until issue #9 is done
