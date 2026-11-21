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
