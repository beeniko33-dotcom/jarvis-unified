# Level 3 pilot run plan (operations readiness, not certification)

**Status: PROPOSED. Counts for nothing toward Level 3.** The verified-day count stays 0 and the 30-day clock stays unstarted
until `PROVENANCE_POLICY_EXCEPTION_PROPOSAL.md` (or a signed-provenance provider) and
`LEVEL_3_TRADING_CALENDAR_PROPOSAL.md` are decided and implemented. Date: 2026-11-15.

## 1. Why run a pilot

Nothing can credit evidence before those decisions, so waiting for them wastes calendar time that could prove the
operations layer. A pilot run on the persistent host, in parallel with the review, means that when the clock can start,
day 1 is not spent finding out that backups, alerts or reconnects do not work. A missed trading day later would restart
the streak, so these defects are cheaper to find now.

The pilot also answers a question the calendar proposal needs: how each feed actually behaves over a weekend.

## 2. Scope and safety

- Candidate-only collection: the Deriv public EURUSD feed and the Biquote candidate adapter, into **separate pilot
  databases** named `pilot-*`. Both are hard-coded `evidence_credit=false`.
- Paper only. No broker credentials, no account endpoints, kill switch engaged, no live adapters.
- Pilot databases are archived at the end and **never imported** into the evidence store. The certified run starts on a fresh
  database, as the store requires one database per configuration. Do not backfill or relabel pilot days.
- Use the runbook's supervisor (`research.collector_supervisor`), host layout and systemd policy in
  `LEVEL_3_PERSISTENT_RUNNER_RUNBOOK.md`, with `HOST_PROVISIONING_CHECKLIST.md` for the machine.

## 3. Preconditions (owner actions, not done by this repo)

1. Reviewer has accepted the operational package (`ROADMAP.md`, immediate sequence item 3), then the host is
   provisioned per the checklist (persistent volume, restricted egress, NTP, unprivileged user, pinned commit).
2. Deriv subscription smoke test passes after the market reopens. The provider reported closed until Monday
   2026-11-16 00:00:00 (provider time), so day 0 is that day at the earliest.
3. Alert routing chosen (a person or channel that is actually read).
4. Biquote terms re-checked for automated collection (`FREE_MARKET_DATA_CANDIDATE_PATH.md`, controls 1 to 7).

## 4. Duration

14 calendar days, so the pilot spans two full weekends. The owner may lengthen it; it should not be shorter than one
weekend plus a full trading week.

## 5. Pass criteria (proposed thresholds; owner may amend before day 0)

| Area | Criterion |
|---|---|
| Supervision | At least 99 percent process uptime during market-open hours. Every restart logged with cause. |
| Coverage | Every market-open UTC day has candidate observations from each feed. Per-day hourly-slot coverage is recorded. |
| Freshness | No stale gap beyond the freshness window during market-open hours, except provider outages that are logged. |
| Integrity | SQLite integrity and hash-chain checks pass daily on both pilot databases. |
| Backup | Daily online backup with recorded hash. One restore drill into a separate directory passes in week 1 (`scripts/sqlite_backup_restore_drill.py`). |
| Alerts | Each runbook alert fires and reaches a person when deliberately triggered once: process kill, stale feed, disk threshold, clock drift. |
| Clock | Measured UTC offset stays inside 1 second (proposed; the runbook leaves the tolerance to be approved). |
| Actions | Broker, account, proposal, order and wallet request count is zero every day. |
| Paper ledger | A daily `scripts/paper_session.py` ledger reconciles cleanly in `scripts/paper_report.py`. |
| Gate | The forward-validation report reads `BLOCKED_PROVENANCE`, `level_3_certification: false`, 0 verified days on every day. Anything else is a bug. |

## 6. Outputs

1. Daily operator record (runbook section 6), archived with the supervisor `--health` JSON.
2. **Weekend closure table**: for each feed, the last tick before close and first tick after reopen, in UTC. This feeds
   the calendar proposal.
3. Divergence log between the two feeds (needs the small read-only comparison script from the exception proposal;
   until it exists, compare daily by hand and record that it was manual).
4. A short pilot report: criteria met or missed, incidents, and what changed before the certified run.

## 7. What a pass does and does not mean

A pass means the host, supervisor, backup, alerting and recovery work for two weeks. It does **not** reduce the 30-day
requirement, count as evidence, or approve any provider. The only effect on the timeline is that the certified run
can start on its first eligible day without ops surprises.
