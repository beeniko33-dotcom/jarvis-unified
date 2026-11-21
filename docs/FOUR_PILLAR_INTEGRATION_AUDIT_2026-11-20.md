# Four-pillar integration audit — 2026-11-20

## Scope and confidence

This is a source-level review of branch `feat/jarvis-four-pillar-architecture`. It does not prove the state of a paused Supabase database, deployed Edge Functions, browser runtime, or production traffic. No database migration, secret, DNS record, production deployment, or destructive operation was performed for this audit.

## Findings

### 1. Forex Signal Intelligence

**Existing:** `research/forex_forecast.py` and `tests/test_forex_forecast.py` provide deterministic bullish/bearish/neutral trend analysis from at least 20 fresh, chronological OHLC candles. The forecast payload has no order-sizing or trade fields. `docs/SIGNAL_INTELLIGENCE_PIPELINE.md` describes the read-only target.

**Blocking:** the current engine is not a verified live FX feed or complete customer-facing Forex app. `docs/FREE_MARKET_DATA_CANDIDATE_PATH.md` explicitly records `BLOCKED_PROVENANCE`, zero verified forward days, and no started 30-day validation period. Candidate Biquote/Deriv observations must not be represented as authenticated market truth. The legacy root runtime and trading migrations remain in the repository; `main.py`, `core/feature_registry.py`, and legacy control-panel UI still contain paper-execution functionality. Do not expose those paths through Forex.

**Next:** isolate a standalone research-only application and ingestion boundary; implement feed adapters only as candidate/unverified until provider provenance and terms are independently reviewed; persist forecast lineage and evaluation separately from legacy trading tables; then remove/retire execution references through a dependency-aware migration with regression coverage.

### 2. Marketplace

**Existing:** `apps/control_panel/marketplace.html`, seller/listing/affiliate/order-intent migrations, and `supabase/functions/marketplace-orders/index.ts` exist. The UI itself describes seller verification, orders as intents, and payments/fulfilment/commissions as inactive.

**Blocking:** the browser application points at the legacy Supabase project URL and its current CORS allowlist is scoped to `jarvis-control-panel.pages.dev` preview/production origins. It is not wired to the separate `jarvis-unified-portal` Pages project. The Supabase project was previously paused; its live availability and migration state have not been re-verified here. Therefore source files are not proof of a working marketplace deployment.

**Next:** move project URL and publishable key into an explicit per-environment public configuration; add the intended app origin(s) to a controlled CORS configuration; verify auth, RLS, Edge Function JWT validation, idempotency, seller verification and order state transitions in an isolated active project; test checkout/order intent only. Payments, fulfilment, commissions and rewards stay disabled until separately reviewed.

### 3. Career

**Existing:** `apps/control_panel/career.html` and Career schema migrations describe candidate profiles, employer onboarding, jobs, applications, and private application messaging. The UI explicitly blocks employer publishing until trusted verification is deployed.

**Blocking:** the UI points at the legacy Supabase project. There are two overlapping foundation migrations: `20261118190000_career_giver_foundation.sql` creates the initial Career tables with `IF NOT EXISTS`, while `20261118193000_career_giver_secure_foundation.sql` creates overlapping table names without `IF NOT EXISTS` and with a changed schema. If both are applied in timestamp order to a fresh database, the later migration will encounter existing tables; if only the later one is applied, the actual migration history and dependency assumptions still need verification. The paused project prevents us from confirming which migrations were applied. This is a release blocker until the migration chain is reconciled against a disposable database and the actual migration history.

**Next:** determine the intended canonical schema, create a forward-only reconciliation migration, test the complete migration chain on a fresh isolated database, run RLS/advisor checks, and verify application/conversation participant isolation. Keep employer verification, external job ingestion and application submission approval-gated.

### 4. JAEO

**Existing:** `research/jaeo_policy.py`, `research/jaeo_commands.py`, tests, `docs/JAEO_SUPERVISED_OPERATIONS.md`, and private-schema migrations define supervised tasks, task-bound approvals, append-only feedback and deny rules. Production deployment, live trading and operator-control changes are denied by policy.

**Blocking:** these are policy and persistence foundations, not a deployed authenticated JAEO service. No active JAEO Edge Function/API, operator dashboard, connected worker, or end-to-end task/approval/feedback lifecycle was verified. The migration documentation itself says the JAEO migration is for the isolated prototype first and the API/dashboard remain future work.

**Next:** implement authenticated task intake and read models, server-side role checks, approval decisions by a distinct human actor, expiry and exact-payload binding, immutable feedback/audit evidence, and safe human-support handoff. Test replay, self-approval, privilege escalation, expired approval and production-resource denial. Do not provision production workers or scheduled jobs as part of this phase.

## Cross-cutting release blockers

1. Supabase target is not established as a healthy isolated runtime; do not apply migrations to the paused production project.
2. Career migration history is ambiguous and overlapping; reconcile before applying the full chain.
3. Marketplace and Career browser apps still target the legacy project and legacy Pages origin.
4. The new static portal is not the app hosting target for the existing control-panel apps; no integration routing was verified.
5. Legacy trading runtime, control panel, schemas and workflows remain. Forex's research-only boundary is not yet enforced repository-wide.
6. No end-to-end browser tests or full security review of all public Edge Functions, RLS policies and database functions was completed.
7. The custom domain remains intentionally unpurchased; free-first hosting remains the constraint.

## Recommended execution order

1. Create an isolated, disposable Supabase project/branch within verified free-tier and budget limits; do not restore or mutate production.
2. Reconcile and test the complete migration chain, starting with Career's duplicate foundation definitions and reviewing all security-definer functions, grants, RLS and CORS.
3. Externalize frontend environment configuration and align allowed origins to the actual application hostnames.
4. Separate Forex research ingestion/forecasting from all legacy execution code and add repository-wide boundary tests.
5. Connect Marketplace and Career to the isolated backend and run authenticated browser/API integration tests.
6. Implement the JAEO authenticated API and dashboard against the supervised schema.
7. Run security advisors, dependency checks, full CI, browser smoke tests and deployment preview checks.
8. Only after evidence is reviewed, request explicit approval for production cutover. Do not merge or deploy automatically.

## Product status correction

Marketplace and Career are not blank projects: their initial UI and schema work exists. They are nevertheless **early foundations, not verified working production services**. JAEO has policy/schema foundations but no verified deployed operator. Forex has a tested forecast engine but no provenance-verified feed or complete app. The public portal remains informational only.


## Deployment follow-up — 2026-11-21

- Cloudflare Pages project `jarvis-unified-portal` successfully built and deployed the latest feature-branch commit `15a4ef7224e2e3c1d92447863ca8ac403ae59e6d`. Preview: https://3fe448f3.jarvis-unified-portal.pages.dev. This is an informational static portal preview, not a four-app production release.
- The legacy `jarvis-control-panel` Pages project also automatically built a branch preview from the same commit: https://985567a7.jarvis-control-panel.pages.dev. Its destination directory is still `apps/control_panel`, which contains the old trading-oriented workspace and the Marketplace/Career pages. This preview pipeline is still connected to all branches. Its project settings were inspected but not changed; disabling previews requires a separately approved Cloudflare configuration change.
- Cloudflare GitHub checks for `jarvis-control-worker` and `jarvis-unified-mcp` failed because those Worker scripts no longer exist in the account. The account's Workers Builds API currently returns no triggers and no build configuration for those script tags. These stale integration checks are distinct from the passing application CI and successful Pages portal build; they need Cloudflare/GitHub integration cleanup.
- The GitHub Actions test jobs for the new audit commit were still in progress at the time of this note. Do not treat the commit as CI-passing until those jobs complete.


## Isolated QA backend validation — 2026-11-21

The user explicitly approved both the legacy Pages preview change and a separate isolated Supabase environment, then confirmed the quoted $0/month project cost.

### Infrastructure actions

- Disabled automatic preview deployments on Cloudflare Pages project `jarvis-control-panel` by setting `preview_deployment_setting=none`. Production deployments remain enabled from `main`; the canonical production deployment was not changed.
- Created Supabase project `jarvis-unified-isolated-qa` in `eu-west-1`, project ref `guvszwxvmitdvykvtsnc`. Supabase reported `ACTIVE_HEALTHY` and quoted $0/month.
- No production Supabase project was restored, modified, or supplied with data. No production secrets, DNS, or custom domain were changed.

### Selected migration validation

The QA database is a curated test target, not a claim that the entire repository migration chain is safe to apply. The following foundations were applied successfully in isolation:

- Career secure foundation (`20261118193000_career_giver_secure_foundation.sql`) and private RLS-helper migration (`20261118210000_hide_career_rls_helpers.sql`).
- Marketplace seller/listing/affiliate/order-intent foundation and service-role-only order RPC hardening.
- JAEO supervised task/approval/append-only feedback foundation and approval expiry.
- Public RLS auth.uid() initialization-plan optimization and a follow-up hardening migration that combines the Career application UPDATE policies, adds the eight missing foreign-key indexes found by the advisor, and revokes API-role execution on the JAEO trigger-only helper.

The older Career foundation migration (`20261118190000_career_giver_foundation.sql`) was deliberately **not** applied. It conflicts with the secure foundation's table definitions. It remains in the repository pending a safe migration-history reconciliation; no previously deployed migration was rewritten.

### Verification results

- Supabase migration history records the selected Career, Marketplace and JAEO migrations plus the two QA hardening steps.
- All 14 application tables created in `public` and `jarvis_private` have RLS enabled.
- The three private JAEO tables have no client-facing RLS policies by design; they are inaccessible to `anon` and `authenticated`, and the private schema/table grants are restricted to `service_role`.
- SQL privilege checks confirmed neither `anon` nor `authenticated` can execute either Marketplace order RPC. The service role can execute the Edge-Function-facing order RPC.
- SQL privilege checks confirmed `authenticated` cannot use `jarvis_private` or read JAEO tasks; `service_role` can.
- A transactional test confirmed the JAEO feedback trigger rejects both UPDATE and DELETE attempts.
- Security advisor: no warning/error findings. The three informational `rls_enabled_no_policy` notices are the expected deny-by-default posture on private JAEO tables.
- Performance advisor after hardening: no remaining `auth_rls_initplan`, multiple-permissive-policy, or unindexed-foreign-key findings. The remaining 23 informational unused-index notices are expected on an empty QA database with no workload.
- Health advisor: no lints.

### Still blocked / not claimed complete

- The full timestamp-ordered repository migration chain has **not** been applied. It includes legacy trading/paper-oriented schema and the overlapping Career migration pair; those require a separately reviewed baseline/reconciliation plan before any production use.
- No authenticated browser/API end-to-end test has yet exercised Career participant messaging or the Marketplace Edge Function against this QA project. No frontend environment variables or secrets have been wired to it.
- JAEO still has no verified deployed authenticated task API/dashboard or end-to-end human approval lifecycle. Its schema foundation alone is not an operator service.
- No production cutover, PR merge, or production deployment was performed.


### Legacy workflow follow-up — 2026-11-21

- The automatic PR preflight for the retired paper prototype attempted to connect using the existing GitHub secret scoped to project `uinibcemffkafdfuewyp`. The connection failed because that paused prototype's database tenant/user was unavailable. The secret value was withheld in logs; no database write occurred.
- The failure was unrelated to the new QA project. The workflow was changed to manual-only so routine four-pillar PRs no longer attempt an automatic connection to the paused paper prototype. Its old project target and read-only checks remain explicitly legacy; do not use it as QA evidence.
- The latest PR head now has a fresh CI cycle. The stale Cloudflare Workers Build checks still report missing Worker scripts; no replacement Worker was deployed.


### JAEO product-boundary correction — 2026-11-21

- Removed the legacy `paper_research` task action and replaced it with `research`; JAEO task envelopes, policy results and learning reports now label their operating mode `supervised`, not `paper`.
- Updated the JAEO operations document to state the current product boundary: research and engineering operations only; no paper, demo or live trading, and no order execution.
- Added and applied `20261121080000_jaeo_supervised_research_mode.sql` to the isolated QA project. Its JAEO task constraint now accepts only `mode='supervised'`; a transactional SQL test confirmed legacy `paper` mode is rejected, `supervised` mode is accepted, and append-only feedback still blocks UPDATE and DELETE after the trigger helper's API grants were revoked.
- JAEO policy, command-routing and learning tests were updated to assert the supervised mode. CI for the resulting head is pending.


### JAEO approval binding hardening — 2026-11-21

- JAEO policy now requires an authenticated requester ID, a different authenticated approver ID, and the exact lowercase SHA-256 request hash before a persisted approval can authorize an action. Missing or mismatched values fail closed.
- Added `20261121090000_jaeo_task_request_binding.sql` and applied it to isolated QA. New task inserts require a requester; approval triggers bind each approval to the task requester, require a different human approver for approve/reject decisions, validate the hash format, and prevent changing task/action/resource/request-hash bindings or revising a final decision.
- A transactional database test verified self-approval is rejected, a distinct approver succeeds, approved bindings cannot be edited, and mismatched requesters/malformed hashes are rejected. The test transaction was rolled back.
- The API/dashboard must still compute the canonical payload hash server-side and submit the requester/approver identities from authenticated sessions. No JAEO API or dashboard is deployed yet.
