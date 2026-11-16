# Supabase durable paper-state adapter

This PR adds a server-side persistence primitive; it does not switch the existing
SQLite paper broker to Supabase and does not start a scheduled trading worker.

## Guarantees
- All persisted account rows hard-code `mode='paper'`.
- A paper cycle commit is one Postgres transaction containing its run-id record,
  append-only hash-chained ledger events, and new account snapshot.
- Account-scoped advisory locking serializes first-time creation and concurrent commits.
- Optimistic revision checks reject stale workers.
- Repeating the same completed run ID with identical account/input/state hashes is
  idempotent; reusing it with different content is rejected.
- Snapshot hashes are checked on load; payloads containing credential-like keys are rejected.
- Browser roles receive no table privileges. Access remains backend-only.

## Not yet enabled
The existing SQLite broker remains the execution simulator of record. The next
integration must map its snapshot and ledger semantics into this adapter and add
round-trip, crash/restart, concurrent-run, and reconciliation tests before a
workflow may invoke it. No broker credentials are required for this adapter.

## Configuration
The backend worker will need `JARVIS_DATABASE_URL` in its encrypted host secret store
and the optional pinned `postgres` dependency. Never put this DSN or broker tokens
in repository files, artifacts, logs, or chat.
