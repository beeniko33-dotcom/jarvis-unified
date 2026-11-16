# Supabase deployment architecture

## Current connected project

Jarvis Unified is connected to a healthy Supabase project in Europe West running PostgreSQL 17.12. Its private schema contains `market_observations`, `runtime_audit_events`, and `worker_heartbeats`. These tables are intentionally outside the browser-facing Data API.

## Target topology

Supabase is the managed data and identity platform, not the always-on Python process host.

- **Supabase Postgres:** durable observations, append-only runtime audit events, worker heartbeats and later normalized execution/accounting records.
- **Supabase Auth:** operator sign-in for a future dashboard/API. Do not expose the service-role key to a browser.
- **Supabase Storage:** later home for exported reports and evidence artifacts, with private buckets and narrowly scoped signed access.
- **Supabase Edge Functions:** short authenticated API endpoints, webhooks and dashboard orchestration only.
- **Python runtime:** keep the collector, paper engine, scheduler, scraper and long-running research workers on a persistent host. These workers connect to Supabase Postgres over TLS using a server-side secret.
- **Dashboard:** static frontend can be hosted separately; it calls authenticated endpoints, never the database service key.

## Postgres evidence adapter (opt-in)

Install the pinned optional dependency with `pip install '.[postgres]'`. Set
`JARVIS_DATABASE_URL` only in the trusted worker's secret manager/environment.
Use the Supabase direct or session-pooler connection string with TLS enabled.
Do not put the DSN, database password, service-role key, or JWT in source control,
dashboard code, CI output, issue comments, or chat.

The adapter is intentionally limited to the existing market-observation contract.
It writes only `candidate_unverified` observations, uses transaction-scoped advisory
locks to serialize per-source ordering checks, deduplicates by the existing unique
(source_id, content_hash) constraint, and reports all evidence as ineligible until
an independent provider verifier exists. It does not migrate the paper ledger or
switch SQLite-backed components automatically.

## Control-plane heartbeat and audit adapter (opt-in)

`research.supabase_control_plane.SupabaseControlPlaneStore` writes worker heartbeat
snapshots and append-only runtime audit events. The read-only status API has an
additional best-effort lifecycle reporter in `research.control_plane_runtime`.
Enable it only with `JARVIS_SUPABASE_CONTROL_PLANE_ENABLED=true` and a backend-only
`JARVIS_DATABASE_URL` in the trusted worker's secret manager. It is disabled by
default and never suitable for browser/mobile clients. Startup, shutdown and periodic
heartbeat writes are best-effort: database failures are logged by exception type
only and must never prevent the local paper status API from serving. A stopped
heartbeat is not proof of a clean shutdown; monitor heartbeat age externally.

Heartbeat writes hard-code `mode='paper'`, reject invalid health values and
out-of-order heartbeat timestamps. Audit events are insert-only and include a
SHA-256 digest of canonical JSON payloads. Both paths reject credential-like
payload keys, enforce payload size/depth limits, and require timezone-aware
timestamps. Do not send raw exception messages or unrestricted process state.

Run the read-only schema diagnostic:

```bash
python scripts/supabase_diagnostic.py
```

It verifies connection, PostgreSQL version, required private tables and RLS state.
It performs no writes and suppresses driver exception strings to avoid leaking DSNs.

## Migration boundary

This is not a completed SQLite-to-Postgres migration. Existing Jarvis modules still
use SQLite and local file paths. Do not switch production reads/writes to Supabase
until each store has a tested adapter, idempotent backfill, reconciliation report,
restart recovery test and rollback procedure. Keep SQLite as the authoritative paper
ledger until that cutover is independently validated.

## Security and operational constraints

- Keep `jarvis_private` outside exposed API schemas; browser roles receive no grants.
- Use a backend-only database credential. Never expose `service_role` or secret keys in a browser.
- RLS is enabled on the three private tables; trusted server-side grants are explicit.
- Do not put credentials, tokens, OTP URLs, wallet secrets or unrestricted exception text in event payloads.
- Keep all broker adapters disabled, the kill switch engaged and execution paper-only.
- A Supabase project does not run the repository's long-lived Python worker.
- No hosting resource is provisioned and no paid service is enabled by this change.
