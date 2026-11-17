# Persistent paper account continuity

Status: simulation only. Nothing here connects to a broker, releases the kill switch by default,
or counts toward the Level 3 gate. Level 3 forward validation is **0 / 30 days**.

## What already existed

`PersistentPaperBroker` (SQLite, `BEGIN IMMEDIATE` writes, SHA-256 chained events, snapshot tied
to the final event, restart restore, crash-before-commit rollback, peak-equity persistence) was
already in place before this change. The JSONL path in `paper_session.py` created a fresh broker
each run, so its ledger file was several independent accounts appended together.

## What this change adds

1. **Account identity.** New accounts record a UUID in the hash-chained genesis event. It is
   stable across restarts and cannot appear later in the chain. Legacy accounts without one are
   reported as a warning and are never rewritten.
2. **Session runner on one account.** `scripts/paper_session.py --account-db PATH` runs against one
   continuous persistent account. Client order IDs are keyed to the UTC day, so a rerun on the same
   day is refused by the observation journal and places no duplicate orders.
3. **Read-only full-history audit.** `research/persistent_account_audit.py` (CLI:
   `scripts/paper_account_audit.py`) opens the database read-only and verifies:
   - the hash chain, recomputed independently;
   - the stored snapshot equals the final event's state;
   - every event's balance moves by exactly realized P&L minus commission, and cumulative realized
     P&L and commission move by the recorded deltas (this is the cross-session reconciliation);
   - timestamps are timezone-aware, ordered, and match their `utc_day`;
   - the account identity is stable;
   - UTC-day coverage of trading events (mark-only days are reported separately and never count).
4. **External anchors.** `--anchor-file` appends `(seq, event_hash)` after a clean audit and checks
   previously recorded anchors on later runs. Store that file where the database host cannot edit it.
5. **Daily verdict.** `scripts/paper_daily_check.py --account-db PATH` is unhealthy on any error or
   warning, including a missing session today, a broken streak, open positions or a legacy account.
6. **Shared day logic.** `research/day_coverage.py` is the one implementation of streak and missing-day
   assessment, used by both the JSONL and account checks.

## Migration policy

- JSONL ledgers are never converted into SQLite accounts, and no existing database is altered.
- An existing SQLite account is opened exactly as before. Its audit reports a warning that no identity
  was recorded.
- `paper_session.py` without `--account-db` behaves exactly as before.
- Archive old ledgers and databases rather than overwriting them.

## Crash recovery: what is and is not automatic

- A crash before the broker commits leaves no position, no fill and no partial state. The audit stays
  verified (covered by `tests/test_crash_safe_account.py`).
- After a crash inside an execution, the decision journal already contains that client order ID, so a
  same-ID retry is refused. This prevents double execution, but it also means **a crashed day cannot
  resume automatically**. An operator must reconcile the attempt and use a new client order ID. Making
  this recovery automatic would need a deliberate design decision.

## Limits

- **Unrealized P&L and equity are not recomputed.** They need market marks that the ledger does not
  store. The audit verifies realized P&L, commission and balance only.
- **A fully consistent rewrite is only detectable with an external anchor.** Without one, a history
  rewritten end-to-end with valid hashes passes the internal checks.
- **Integrity is not market authenticity.** A verified account says nothing about whether its prices
  came from a licensed provider. Paper session prices are fixed synthetic fixtures.
- **Trading days in this account never count toward Level 3.** The daily check reports this explicitly.

## Operating it

```bash
python scripts/paper_session.py --allow-entries --account-db var/paper_account.sqlite3
python scripts/paper_account_audit.py var/paper_account.sqlite3 --anchor-file var/paper_account.anchors.jsonl
python scripts/paper_daily_check.py --account-db var/paper_account.sqlite3
```

Back up the database with SQLite's online backup while it is running, as described in
`docs/PERSISTENT_PAPER_LEDGER.md`. Do not copy only the main file while WAL writes may be pending.
