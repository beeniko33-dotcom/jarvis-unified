# Supabase deployment architecture

## Target topology

Supabase is the managed data and identity platform, not the always-on Python process host.

- **Supabase Postgres:** durable observations, append-only runtime audit events, worker heartbeats and later normalized execution/accounting records.
- **Supabase Auth:** operator sign-in for a future dashboard/API. Do not expose the service-role key to a browser.
- **Supabase Storage:** later home for exported reports and evidence artifacts, with private buckets and narrowly scoped signed access.
- **Supabase Edge Functions:** short authenticated API endpoints, webhooks and dashboard orchestration only.
- **Python runtime:** keep the collector, paper engine, scheduler, scraper and long-running research workers on a persistent host (the existing host plan prefers an Oracle Cloud Always Free VM with persistent disk). These workers connect to Supabase Postgres over TLS using a server-side secret.
- **Dashboard:** static frontend can be hosted separately; it calls authenticated endpoints, never the database service key.

## Why not put the whole runtime in Edge Functions?

Supabase Edge Functions use a Deno/TypeScript runtime, not the repository's Python runtime. Hosted limits include 256 MB memory, 2 seconds CPU per request, and a wall-clock duration of 150 seconds on Free / 400 seconds on paid. A continuous WebSocket market collector and a 30-day validation process must not depend on an Edge Function staying alive. Supabase documents Compute as private alpha; do not treat it as a generally available production host.

## Migration

Apply SQL migrations with the Supabase CLI after creating a project and linking its project ref:

```bash
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

This migration creates a non-exposed `jarvis_private` schema with:
- append-only market observations whose provenance is constrained to `candidate_unverified`;
- append-only operational audit events;
- mutable worker heartbeat snapshots constrained to `paper` mode.

RLS is enabled, browser roles have no table privileges, and only the server-side `service_role` receives the required grants. Never put the service-role key in dashboard code, mobile apps, source control, or chat. Do not put credentials, tokens, OTP URLs, or unrestricted exception text in event payloads.

## Important migration boundary

This is a control-plane schema foundation, not a completed SQLite-to-Postgres migration. Existing Jarvis modules still use SQLite and local file paths. Do not switch production reads/writes to Supabase until each store has a tested adapter, idempotent backfill, reconciliation report, restart recovery test and rollback procedure. Keep SQLite as the authoritative paper ledger until that cutover is independently validated.

## Required deployment sequence

1. Create a Supabase project and select a region close to the persistent worker where possible.
2. Store the project URL, database connection string and service-role credential in the worker host's secret manager; use a dedicated restricted database role in preference to broad credentials once the adapter supports it.
3. Apply migrations to a fresh project and verify schema grants, RLS and append-only triggers.
4. Implement a Postgres repository adapter for market observations and heartbeats; add integration tests against a disposable Supabase/Postgres instance.
5. Migrate audit events and reports with hash/row-count reconciliation and restore drills.
6. Only then migrate paper ledger / reservations / contract lifecycle, preserving transaction and idempotency guarantees.
7. Deploy authenticated dashboard endpoints and Storage policies. Do not expose the existing unauthenticated localhost status API publicly.
8. Run paper-only soak tests and backup/restore drills before starting any forward-evidence clock.

## Backups

Supabase Free projects should regularly export data using `supabase db dump` and store encrypted off-site copies. Automated daily backups and point-in-time recovery depend on paid plan eligibility. Backups do not replace a tested restore drill.
