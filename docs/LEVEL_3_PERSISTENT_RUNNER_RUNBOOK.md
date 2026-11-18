# Level 3 persistent paper-only collector — operations runbook

**Status: preparation only. No host has been provisioned and no deployment has been performed.** This runbook is for a future persistent runner after provenance implementation and independent review.

## 1. Safety and scope

- Run only the Deriv public EURUSD market-data WebSocket collector (or other explicitly approved candidate feeds).
- No account token, App ID, OTP, demo/real account endpoint, wallet, proposal, buy, sell or broker execution.
- Keep all broker adapters disabled and the paper kill switch engaged.
- Market-data observations are not fills or strategy performance. Maintain a separate paper execution ledger for fills, spread/cost assumptions, fees, slippage, positions and PnL.
- Do not start the 30-day Level 3 clock until the provenance gate has been independently approved and the first authenticated observation is accepted.

## 2. Host requirements

- A continuously available Linux host or equivalent supervised runtime.
- Persistent encrypted disk/volume for SQLite database, WAL files and append-only backup snapshots. Never use an ephemeral CI runner as the evidence host.
- Dedicated unprivileged OS account; repository checkout pinned to a reviewed commit.
- Reviewed runtime baseline: CPython 3.11.18. Install the runtime-only, pinned market-data dependency subset with `python -m pip install "pip==26.3" -r requirements-market-data.lock`. CI/test environments use the complete pinned set in `requirements-lock.txt`.
- UTC clock synchronization using a monitored time service. Alert on drift beyond the programme's approved tolerance.
- Outbound network access restricted to DNS and the approved public WSS hostname/port. No inbound public listener is required for collection.
- Disk capacity sized for raw payload retention, WAL growth and backups; alert before low-space conditions.
- No secrets are required for the public market-data endpoint. Do not add broker credentials to this host.

## 3. Process supervision

Use the continuous session supervisor (`python -m research.collector_supervisor`) under a system supervisor (systemd or equivalent). The supervisor:

- Runs duration-bounded collector sessions sequentially.
- Holds an exclusive file lock so two writers never touch the same SQLite database.
- Breaks **stale locks** when the recorded owner PID is no longer alive.
- Applies **exponential backoff** after consecutive failures and stops after a configurable failure budget.
- Handles **SIGTERM / SIGINT** cooperatively so the continuous loop exits cleanly.
- Records every session boundary (start/end, exit code, command, status) as JSON.
- Exposes a lightweight `--health` snapshot for operators (not market-data evidence).

Example service policy (adapt and review before installation):

```ini
[Unit]
Description=Jarvis Deriv public EURUSD paper-only market data collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=jarvis-collector
Group=jarvis-collector
WorkingDirectory=/opt/jarvis-unified
# Supervisor options must precede --command. Every token after --command
# is forwarded unchanged to the collector process.
ExecStart=/opt/jarvis-venv/bin/python -m research.collector_supervisor \
  --db /var/lib/jarvis/deriv_eurusd_forward.sqlite3 \
  --duration-seconds 86400 \
  --log-dir /var/lib/jarvis/sessions \
  --pause-between 15 \
  --max-consecutive-failures 5 \
  --backoff-base 15 \
  --backoff-cap 300 \
  --command /opt/jarvis-venv/bin/python -m research.deriv_feed --duration-seconds 3600 --db /var/lib/jarvis/deriv_eurusd_forward.sqlite3
Restart=on-failure
RestartSec=15
KillMode=control-group
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/jarvis
UMask=0077

[Install]
WantedBy=multi-user.target
```

Operator health check (no collector started):

```bash
python -m research.collector_supervisor \
  --db /var/lib/jarvis/deriv_eurusd_forward.sqlite3 \
  --log-dir /var/lib/jarvis/sessions \
  --health
```

The supervisor itself is the reviewed loop that schedules bounded sessions, records boundaries, and avoids overlapping writers. Do not assume a bare duration-bounded collector provides continuous 30-day coverage.

## 4. Health, freshness and alerting

Emit structured health records with host ID, commit SHA, process start, collector version, endpoint, session ID, connection state, last provider event time, last receive time, UTC clock offset, database path/size, WAL size, last successful backup and current provenance gate.

The supervisor `--health` output covers process-level facts (lock state, last session record, session count). It is **not** a substitute for feed-freshness or provenance checks.

Alert on:
- process exit or repeated reconnects;
- supervisor stop after consecutive-failure budget;
- no tick within the approved freshness window;
- missed UTC observation day;
- TLS/certificate/hostname verification failure or unexpected peer change;
- clock drift or future/stale provider timestamps;
- broken audit hash chain or database integrity failure;
- disk-space threshold, WAL growth or failed backup;
- backup age beyond the approved interval;
- unexpected binary/commit/configuration change;
- any broker adapter or account endpoint becoming reachable/enabled.

A heartbeat proves process liveness only. It is not a market observation and does not count toward coverage.

## 5. Durable storage and backups

- Keep SQLite WAL mode and FULL synchronous durability as configured by the reviewed store.
- Use SQLite's supported online backup mechanism or a quiesced, consistent snapshot; do not copy only the main database while WAL writes are active.
- Encrypt backups at rest, restrict access, retain immutable/append-only copies and record backup hashes, timestamps and source commit.
- Perform a restore drill into a separate directory/database. Verify SQLite integrity, event-chain integrity, record counts, latest observation, configuration and provenance decisions.
- A successful backup without a successful restore drill does not satisfy operational acceptance.
- Never rewrite or backfill missing observation days. A missing day breaks the consecutive-day streak.

## 6. Daily operator evidence checklist

For every UTC day, retain a timestamped record containing:

1. **Process identity:** host ID, supervisor PID, collector PID, repository commit SHA, Python version, collector command and config hash.
2. **Session boundaries:** session ID, UTC start/end, exit code, status, restart count and lock owner.
3. **Feed freshness:** endpoint, instrument, last provider event timestamp, last receive timestamp, age of last tick and stale/future/reconnect counts.
4. **Clock:** NTP source, measured UTC offset and synchronization status.
5. **Storage:** database size, WAL size, free disk space, configured headroom threshold and SQLite/hash-chain integrity result.
6. **Backup:** backup path/identifier, UTC completion time, SHA-256 backup hash, source commit and last successful restore-drill result/date.
7. **Provenance:** provider verification status, verified/unverified candidate counts and current evidence gate.
8. **Actions:** explicit count of broker/account requests, proposals, orders and wallet actions; expected value is **zero**.
9. **Incidents:** outage, reconnect, missed day, configuration change, lock recovery, process crash or alert and the operator response.
10. **Archive:** save the supervisor `--health` JSON and the signed/controlled daily operations record with the collector logs.

A process heartbeat is not a market observation. A backup hash is not a restore result. A restore result is not provider provenance. Keep these evidence classes separate.

## 7. Acceptance before starting the 30-day clock

- Provenance implementation merged only after explicit authorization and independently reviewed; this runbook itself does not authorize a merge.
- Persistent host and storage are available and documented.
- Supervision, clock sync, monitoring and alert routing are tested.
- Backup and restore drill passes.
- First real public Deriv tick is received through the reviewed authenticated session and accepted by the trusted verifier.
- Independent reviewer signs the operational evidence package with host configuration, commit, session proof, raw observation digest and restore evidence.

Until all conditions pass, the forward-validation day count remains zero. CI fixtures, replay, synthetic tests, process heartbeats and unverified candidates are not credited.
