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
- [ ] Worker preview tested with exact Wrangler version, working directory, and config path recorded.
- [ ] Cost estimate fits free-first target and hard ceiling of NGN 5,000/month.
- [ ] Daily evidence package and reconciliation report verified.
- [ ] Separate explicit approval obtained before any production deployment.
- [ ] Kill switch remains engaged and entries remain paused until a separate safety review authorizes a change.

## Deployment note

Do not assume Cloudflare Worker is the correct host for the Python/Postgres runner. First compare available hosting options against persistent process support, outbound TLS Postgres access, secret management, sleep/idle behavior, observability, and the NGN 5,000/month ceiling. If no suitable free-tier host meets all requirements, keep the runner un-deployed and provide a local/manual supervised test path rather than weakening integrity or safety requirements.
