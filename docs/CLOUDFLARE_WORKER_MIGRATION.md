# Cloudflare worker migration

## Stage 1 — command controller

`cloudflare/worker.py` is the Cloudflare Python Worker entrypoint. A one-minute UTC Cron Trigger polls the existing Supabase command queue, atomically claims allowlisted commands, persists operator state in the existing `operator_status` row, and reports a heartbeat.

Supported in this stage:
- `pause_entries`
- `resume_entries` only when the kill switch is already disengaged
- `engage_kill_switch`

`run_paper_session` is deliberately rejected with an explicit migration-pending reason. No local script is launched and no synthetic fills are represented as real market evidence.

## Required Cloudflare secrets

Set these in the Cloudflare dashboard under Workers & Pages → jarvis-control-worker → Settings → Variables and Secrets:
- `SUPABASE_SERVICE_ROLE_KEY` — store as a Secret, never as a plaintext variable.

`SUPABASE_URL` is a non-secret variable in `wrangler.jsonc`. Do not commit service-role or secret API keys.

## Stage 2 — persistent paper execution (not yet enabled)

The existing `research/control_worker.py` and `scripts/paper_session.py` use local files, SQLite, and subprocess execution. They must not be called from a Cloudflare Worker as if those resources were durable or equivalent.

Before enabling `run_paper_session`, migrate the persistent paper account, observation journal, risk state, idempotency keys, and transactional execution boundary to Postgres. Add atomic database functions for session claiming, order decision/fill journaling, daily session uniqueness, and crash reconciliation. Validate parity against the current Python test suite and add concurrency/restart tests. Only then may the command be enabled.

## Safety invariants

- Paper mode only; live trading is not implemented.
- A missing status row initializes to paused + kill switch engaged.
- A remote command cannot release the kill switch.
- A remote resume is rejected while the kill switch is engaged.
- Unknown actions are never claimed.
- The paper-session command is explicitly rejected until Stage 2 is verified.
- Secrets are only read from Cloudflare's secret environment.
