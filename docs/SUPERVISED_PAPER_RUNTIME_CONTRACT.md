# Supervised paper-runtime implementation contract

Status: engineering specification only. This document does not enable or deploy a trading runtime.

## Non-negotiable operating boundary

- Execution mode is paper-only, enforced in code rather than selected by an environment toggle.
- The operator kill switch remains engaged and entries remain paused by default.
- The session runner has no capability to resume entries, disengage the kill switch, sign wallet transactions, or call exchange order endpoints.
- Gate.io access is public/read-only market data only. Do not load or use the user's private trading API token in the runner.
- Unverified market observations have zero evidence credit and cannot authorize a paper entry.
- Missing configuration, stale data, clock skew, out-of-order candles, failed integrity checks, or database errors fail closed.
- No production deployment or control-state mutation is authorized by this specification.

## Repository facts checked on 2026-11-19

- `research/supabase_paper_state.py` provides a Postgres adapter with transaction-scoped account advisory locks, revision checks, UUID run idempotency, atomic run/snapshot/event writes, state hashes, and event-chain verification.
- `supabase/migrations/20261116190000_durable_paper_state.sql` defines private paper account, run, and append-only ledger tables.
- `cloudflare/worker.py` is a Python Workers control/market-ingress component. It intentionally rejects `run_paper_session` and reports `disabled_pending_postgres_migration`.
- The current Cloudflare Worker should remain a control-plane and read-only ingress component. Do not put a psycopg-backed session runner in it without a separately proven compatible runtime and dependency model.
- Current market-analysis output is research-only/unverified; it is not suitable for performance evidence or entry authorization.
- Existing local paper-session scripts using SQLite or fixture prices are tests/research tools, not production-like Gate.io forward evidence.

## Required architecture

1. **Read-only market collector**
   - Fetch only public Gate.io market endpoints.
   - Normalize instrument, timeframe, candle open/close times, source timestamp, receive timestamp, bid/ask if available, and source identity.
   - Reject incomplete candles, stale observations, clock skew, duplicate/out-of-order records, malformed values, and unsupported symbols.
   - Persist raw normalized observations and provenance metadata. Do not infer provenance from a symbol or a successful HTTP response.

2. **Trust and eligibility gate**
   - Require source identity, retrieval timestamp, event timestamp, content hash, schema version, and deterministic validation result.
   - Keep `candidate_unverified` / `provenance_verified=false` observations at zero evidence credit.
   - A boolean field in an observation is never proof of provenance. The cycle planner requires an Ed25519 signature over the canonical normalized observation, verified against a public key supplied by trusted runtime configuration (never a key embedded in the observation). The private signing key belongs only to the independently operated verifier; do not place it in the runner or GitHub repository.
   - Do not turn a research signal into a paper order unless a separately reviewed policy explicitly enables paper simulation and all risk checks pass.
   - Missing bid/ask must remain missing; do not relabel a candle close as an executable quote.

3. **Supervised Python paper runner**
   - Run on a persistent host that supports the repository's pinned Python version, psycopg dependency, TLS Postgres connectivity, durable secret injection, process supervision, health checks, and bounded cost.
   - The runner loads the paper account snapshot and verifies its state hash and complete ledger before calculating a cycle.
   - The runner consumes only validated market observations, computes a deterministic input fingerprint, and uses a UUID idempotency key.
   - A completed cycle commits state and append-only events through `SupabasePaperStateStore.commit_cycle`.
   - On any error, no partial state is committed; restart loads the last committed snapshot and verifies the ledger.
   - The runner must not contain exchange order clients, wallet signers, or private trading credentials.

4. **Operator control boundary**
   - The worker and database operator state remain the source of the kill-switch and entry-pause status.
   - A session may not run while kill switch is engaged or entries are paused.
   - This task does not include a resume or kill-switch-disengage operation. Those remain separate, explicit operator actions after validation and review.
   - Any unavailable or contradictory control state is treated as blocked.

5. **Evidence and reconciliation**
   - Each run emits a hashed manifest containing code commit, strategy version, input observation IDs and hashes, market trust state, account revision before/after, run UUID, ledger event range, state hash, risk decision, and timestamps.
   - Daily report reconciles run rows, account revision, ledger sequence/hash tail, market observation provenance, and runtime heartbeat.
   - Prototype smoke tests are excluded from forward-validation statistics.
   - Start the 30-day forward-validation clock only after the first complete run passes independent reconciliation and is explicitly marked eligible.

## Required test matrix

- Idempotent replay: same UUID and identical input/state produces no additional run or event rows.
- Conflicting replay: same UUID with different account/input/state is rejected.
- Stale revision: concurrent writers cannot overwrite a newer account revision.
- Concurrent first-account creation: advisory lock serializes creation and first commit.
- Transaction rollback: injected failure between run/event/snapshot writes leaves no partial committed cycle.
- Restart recovery: a fresh process loads the exact prior state and verifies the ledger.
- Tampering: changed payload, timestamp, previous hash, event hash, missing sequence, missing event, orphan run, or inconsistent last-run reference is rejected.
- Market quality: stale, incomplete, out-of-order, clock-skewed, duplicate, unsupported, and unverified observations cannot produce eligible entries.
- Controls: engaged kill switch, paused entries, missing control row, or contradictory controls reject execution.
- Safety static checks: no broker order imports, wallet signing, exchange private endpoints, or live execution routes in runner dependency graph.
- Evidence: prototype and synthetic fixtures never count as forward observations.

## Release gates

- [ ] Runner implementation reviewed and covered by unit/integration tests.
- [ ] Disposable paper account end-to-end test passes.
- [ ] Duplicate replay produces exactly zero additional ledger events.
- [ ] Crash/restart recovery and hash-chain verification pass.
- [ ] Gate.io observation provenance independently validated; unverified observations remain ineligible.
- [ ] Independent verifier key custody, rotation, revocation, and attestation issuance are reviewed before a trusted public key is configured.
- [ ] Verifier integration tests prove 50 contiguous candles, signed best bid/ask, TLS host validation, and tamper rejection; no private key is present in runner or CI.
- [ ] Worker preview tested with exact Wrangler version, working directory, and config path recorded.
- [ ] Cost estimate fits free-first target and hard ceiling of NGN 5,000/month.
- [ ] Daily evidence package and reconciliation report verified.
- [ ] Separate explicit approval obtained before any production deployment.
- [ ] Kill switch remains engaged and entries remain paused until a separate safety review authorizes a change.


## Cost-constrained host decision (reviewed 2026-11-19)

Use a **bounded Render Cron Job** as the preferred candidate for the eventual Python/Postgres cycle worker, subject to account setup and a measured cost check. Do not use a permanently running background worker at this budget.

- Render Cron Jobs can run a repository command on a cron schedule, receive environment variables/secrets, and are guaranteed to have at most one active run per job. If a run overlaps its next scheduled time, the next run is delayed until the active one finishes. A run is forcibly stopped after 12 hours; it cannot mount a persistent disk, so all durable state must remain in Supabase Postgres.
- The smallest published cron compute tier is 0.5 CPU / 512 MB at USD 0.00016 per active minute, with a USD 1/month minimum per cron service. A five-minute schedule over a 30-day month produces 8,640 runs. At a measured one-minute runtime per run, compute is USD 1.3824/month (minimum charge does not increase this); at the 2026-11-19 indicative rate of about NGN 1,351/USD, that is about NGN 1,868 before card/FX fees and tax. To remain under NGN 5,000 at that rate, average active runtime must stay below about 2.68 minutes per run, before fees/tax. Enforce a monthly spend guard and stop scheduling before the budget is breached. This is a planning estimate, not an account quote; measure real run durations and use the actual billing rate.
- Enforce a hard per-run timeout and a monthly spend guard; if observed runtime or billing forecast threatens NGN 5,000/month, pause scheduling and require review. No automatic upgrade to a larger tier.
- GitHub Actions remains the CI and manual diagnostic path. It is free for standard hosted runners in public repositories, but scheduled workflows have a five-minute minimum, may be delayed or dropped under load, and public-repository schedules are disabled after 60 days without repository activity. It is therefore not the primary evidence scheduler.
- The Render job must use a short-lived run: read controls, validate the feed, verify account/ledger, execute at most one deterministic paper cycle when all independent gates pass, commit atomically, emit a reconciliation manifest, and exit. It must not depend on local files or process memory for recovery.

The host is **not deployed or connected** by this decision. Before provisioning, verify the account's actual plan, runtime, billing alerts, environment-variable handling, Postgres TLS connectivity, and final NGN conversion. The runner stays blocked until the independent market-data and operator gates pass.

## Deployment note

Do not assume Cloudflare Worker is the correct host for the Python/Postgres runner. First compare available hosting options against persistent process support, outbound TLS Postgres access, secret management, sleep/idle behavior, observability, and the NGN 5,000/month ceiling. If no suitable free-tier host meets all requirements, keep the runner un-deployed and provide a local/manual supervised test path rather than weakening integrity or safety requirements.


## Gate.io public API response contract (reviewed 2026-11-19)

- Gate.io API v4 `GET /spot/time` returns `server_time` in Unix milliseconds; normalize by dividing by 1,000 before deriving candle timestamps and compare the full millisecond value for clock skew.
- `GET /spot/candlesticks` returns arrays of string fields. The documented response example has six fields; candle close is index 2 and the open timestamp is index 0. Do not require a seventh field.
- `GET /spot/order_book` returns bid/ask levels as [price, quantity] arrays, not objects with a `p` property.
- The verifier must timestamp `received_at` after completing the three public fetches, not before network I/O.
- Reference: https://www.gate.com/docs/developers/apiv4/en/spot/ and https://www.gate.com/docs/apiv4/index.html
- Live endpoint reachability has not been confirmed from the current engineering environment; the verifier remains mock-tested only until an isolated read-only run is completed.


## Render deployment readiness check (2026-11-19)

- The repository currently has no `render.yaml`, no `Procfile`, and no `scripts/run_paper_cycle.py` entrypoint.
- The existing `Dockerfile` starts the long-running web process with `python main.py --serve`; it does not install the optional Postgres extra. It is not a valid Cron Job command as-is.
- Do not point Render Cron at the current Dockerfile command. Before provisioning, add a dedicated one-shot runner that reads operator controls and the signed verifier output, verifies the account/ledger, calls the orchestrator once, writes a reconciliation manifest, and exits.
- The eventual Cron build must install the Postgres extra (for example `pip install '.[postgres]'`) and pin its Python/runtime dependencies. It must use Supabase Postgres for durable state; Render Cron has no persistent disk.
- Required environment variables must be allowlisted and validated at startup. The runner may receive only the pinned verifier public key and a TLS Postgres connection string; never the verifier private key or Gate.io private trading credentials.
- Deployment remains blocked pending the runner entrypoint, external verifier key custody/rotation/revocation, real read-only Gate.io endpoint validation, and a confirmed Render workspace/billing limit. No Render service or production schedule was created.


## Independent Gate.io attestor and one-shot runner (2026-11-19)

### Signing-key custody

- A dedicated Cloudflare Worker named `jarvis-gateio-attestor` now holds the Ed25519 signing private key as a Cloudflare `secret_key` binding named `JARVIS_GATEIO_SIGNING_KEY`. The key is imported as a non-exportable runtime `CryptoKey`; its value is not returned by the secret-binding API and is not stored in GitHub, Supabase, the runner, or the repository.
- The corresponding raw Ed25519 public key is pinned in `config/gateio-verifier-public-key.b64`. SHA-256 fingerprint: `42936b2d597262781bed1e7ebbe895cdbc53e578916cf83ba66218a907a30cd5`.
- Public endpoint: `https://jarvis-gateio-attestor.beeniko33.workers.dev/v1/attestation`. It accepts GET only, fetches fixed BTC_USDT public spot endpoints, and returns a signed snapshot. It has no private exchange API, order, wallet, database-write, or operator-control functionality.
- The endpoint is public because the payload contains only public market data. Do not send it secrets or account information. Add an authenticated access gate/rate limit before increasing usage or relying on it as a shared production service.
- Rotation/revocation is not automated. For an emergency revoke, disable the Worker subdomain and remove/replace the secret binding; then replace the pinned public key in a reviewed change and update runner configuration. Keep evidence credit false until key identity, rotation, revocation, and independent review are formally accepted.

### Live verification

- `scripts/verify_gateio_attestor_live.py` fetches the Worker endpoint, checks its host, verifies the Ed25519 signature using the repository-pinned public key, and passes the observation through the research planner with synthetic healthy controls. It does not connect to Supabase or write paper state.
- Live GitHub Actions run #4, `44584259445`, succeeded on 2026-11-19. It received BTC_USDT 5m public data, verified the signature, and returned a non-executable `EXIT_CANDIDATE`. `orders_submitted=0`, `provenance_verified=false`, and `evidence_credit=false`.
- This is a successful live feed/signature check, not permission to trade and not a 30-day forward-validation sample.

### One-shot Postgres runner

- Entrypoint: `python -m scripts.run_paper_cycle_once`.
- Required environment: `JARVIS_DATABASE_URL` (TLS required), `JARVIS_PAPER_ACCOUNT_ID`, and optionally `JARVIS_GATEIO_VERIFIER_PUBLIC_KEY_B64` (otherwise the pinned repository key is used).
- The default signed-snapshot URL is the pinned Cloudflare attestor endpoint. An alternate file input is supported for isolated tests only.
- Before fetching market data or loading a paper account, the runner reads the latest `public.operator_status` row for `cloudflare-control-worker`. Missing, stale (>180 seconds), unhealthy, non-paper, kill-switch-engaged, or entry-paused controls exit blocked with no account/ledger write.
- When controls permit, the runner fetches one signed observation, validates the attestation in the planner, verifies account/ledger integrity, commits one research-only event atomically, prints a sanitized report, and exits.
- It never submits orders or changes operator controls. The production controls were last observed as `health=blocked`, `mode=paper`, `kill_switch_engaged=true`, `entries_paused=true`; therefore a production invocation currently exits blocked before any market fetch or commit.

### Release and hosting

- Disposable Postgres integration run #14 and the live attestor run #4 are separate checks. The full CI run for the latest runner commit is pending at time of this documentation update.
- Render Cron is not provisioned. The repository has a dedicated one-shot entrypoint now, but actual Render workspace plan, payment method, spending controls, and account-level monthly cap cannot be verified until the Render connection is authorized.
- Budget estimate remains a planning estimate: 8,640 monthly runs at 1 minute each = 8,640 active minutes, about USD 1.38/month at the published compute rate, before taxes/FX/payment fees. The service must enforce a monthly spend stop and average runtime below approximately 2.68 minutes per five-minute run to stay within NGN 5,000 at the indicative FX rate.


### Render Blueprint and bounded compute estimate

- `render.yaml` defines a Frankfurt Cron Job on `0.5c-512mb`, every five minutes, building the `.[postgres]` extra and running `python -m scripts.run_paper_cycle_once`.
- The start command uses GNU `timeout` with an 85-second TERM deadline and a 5-second KILL grace period. This bounds scheduled active compute to at most 90 seconds per run; a killed database transaction rolls back on connection close. The command is intentionally one-shot.
- Supabase is in `eu-west-1`; Frankfurt is the nearest Render region available in the documented Render region list.
- 30-day maximum scheduled compute at the 90-second cap: 8,640 runs × 1.5 minutes = 12,960 active minutes × USD 0.00016 = USD 2.0736. A 31-day month is USD 2.14272. At an indicative USD/NGN rate around 1,352.5, that is approximately NGN 2,803 (30 days) or NGN 2,897 (31 days), before bank/card FX spread and taxes. At one minute average, 30-day compute is USD 1.3824 (about NGN 1,870). Render also applies a USD 1/month minimum per Cron service.
- Render Cron Jobs are paid compute even on the free Hobby workspace; the workspace plan itself may be free, but this does not make the Cron service free. The 90-second timeout caps normal scheduled run cost but does not constitute a workspace-wide compute spend cap.
- Render documents a spend limit for build-pipeline minutes, not a general monthly compute cap for Cron services. The actual workspace plan, payment method, billing usage, and any spend controls cannot be verified until the Render app is connected and its Billing/Workspace settings are inspected.
- The Blueprint is configuration only. It has not been applied, no Render service was created, and no paid resource was provisioned.
