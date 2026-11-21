# Jarvis Autonomous Engineering & Operations (JAEO)

## Configured operating mode

- Autonomy: **supervised**
- Task mode: **research and engineering operations only**
- Workspace scope: **all** (discoverable connected workspaces; not a claim that every provider is connected)
- Feedback: **both** dashboard and reports
- Trading: **no paper, demo, or live trading; no order execution**
- Production operator controls: immutable to JAEO
- Budget: plan for no more than **₦5,000/month**; paid provisioning is blocked until current account billing and total exposure are verified.

## Agent roles

Orchestrator, Engineering, Database, Infrastructure, Security, QA, Research, Release and Audit are policy roles. A role name does not itself create an external model, worker, credential or provider connection. Each provider must be separately connected and verified.

## Permission model

Low-risk inspection, research, tests, branch creation and pull-request preparation can proceed. Code changes, schema changes, secret changes, provisioning, Cron creation, preview deployments and merges require explicit human approval recorded against the exact task, action, resource and canonical payload hash. The requester cannot approve their own request; the approver must be a different authenticated human. Production deployments, production operator-control changes and all trading actions are denied even if an approval is supplied.

Forex Signal Intelligence is read-only research. JAEO may organize observations, tests and engineering work, but it cannot create trade signals with execution instructions, orders, positions, sizing, entries, exits or broker requests. Never place credentials in task payloads or feedback.

Production resource identifiers are denylisted, including the production Supabase project and production control Worker.

## Task and feedback lifecycle

Tasks use a durable UUID, unique idempotency key, authenticated requester, explicit agent role, workspace scope, fixed supervised autonomy and dashboard-plus-report feedback. Approval rows are bound to the task requester and immutable action/resource/request hash; database triggers reject self-approval and edits after a decision. Feedback records capture status, inspected/changed resources, tests, deployment state, errors, evidence URLs and recommendations. Feedback is append-only. Learning reports are proposals for human review; they cannot change policy or self-modify.

## Integration truth

Read-only access is verified for the GitHub repository, the isolated Supabase QA project, and the Cloudflare account. Production Supabase projects remain paused and untouched. Legacy trading Workers and execution paths are not part of the four-pillar research-only release.

Render is not verified as connected; therefore Render workspace inspection, Cron creation, deployment and billing checks cannot be reported as completed. No JAEO Worker or JAEO Cron has been provisioned. A configured role is not a connected integration, and each write/deploy operation remains approval-gated.

## API implementation status

- An authenticated Edge Function source now exists at `supabase/functions/jaeo-operator/index.ts`.
- It verifies bearer sessions with `auth.getUser(token)`; requester identity comes only from that verified user.
- Operator decisions require the trusted `app_metadata.jaeo_operator === true` claim. User-editable metadata is not used for authorization.
- The function computes a canonical SHA-256 hash server-side and calls a service-role-only RPC. The private `jarvis_private` schema remains unexposed; browser roles cannot execute the RPC or use the private schema.
- The RPC migration `20261121110000_jaeo_operator_rpc.sql` has been applied to isolated QA and verified for create-task, approval-request, self-approval rejection, distinct-operator approval, and rollback-only lifecycle behavior.
- The API records approval decisions only. It does not execute code changes, schema changes, deployments, merges, provisioning, or any trading action.
- The Edge Function is **not yet deployed**. Deployment requires an explicit preview/deployment approval and a configured allowlist of the intended QA portal origin(s). No operator has been granted the `jaeo_operator` app-metadata claim yet.
- The browser dashboard and end-to-end invocation test remain pending; the current test verifies the source-level auth and RPC boundary.

## Rollout sequence

1. Apply JAEO schema and server-only RPC migrations to isolated QA only. **Done.**
2. Verify grants, RLS, constraints and security advisors. **Done; only the three intentional private-table no-policy informational notices remain.**
3. Run repository regression tests and PR CI. **Earlier head passed; latest API changes are awaiting a new CI run.**
4. Deploy the authenticated API to isolated QA only after explicit deployment approval and QA-origin allowlist configuration.
5. Provision operator app-metadata claims only for named, authorized human operators through a separately reviewed admin process.
6. Build the authenticated dashboard and run full browser-to-Edge-Function E2E tests, including expired approval, replay, self-approval, privilege escalation and production-resource denial.
7. Connect provider adapters with least privilege and audit evidence; keep production and trading controls untouched.

No production deployment, paper validation, live trading, or 30-day paper-validation start is implied by this implementation.


## Isolated QA rollout — 2026-11-21

- The authenticated Edge Function `jaeo-operator` is deployed to isolated project `guvszwxvmitdvykvtsnc`, version 3, with gateway JWT verification enabled.
- It supports task create/list, approval request/list, approval decision and append-only feedback. Operator approval queue visibility is role-gated. The Edge Function verifies the bearer token with Supabase Auth and trusts only `app_metadata.jaeo_operator`.
- The function supports both legacy Supabase key environment variables and the current JSON-backed `SUPABASE_PUBLISHABLE_KEYS` / `SUPABASE_SECRET_KEYS` environment variables. No secret key is present in browser source.
- The server-only RPC was extended with requester-scoped approval listing and operator-wide queue listing; migration `20261121120000_jaeo_approval_queue.sql` is applied to isolated QA.
- The static JAEO console is available at `apps/portal/jaeo.html`, with a public publishable key for isolated QA in `apps/portal/jaeo-config.js`. It supports signup/sign-in, task creation, task listing, approval requests, and operator-only approval decisions. No operator app-metadata claim has been provisioned; no user is automatically made an operator.
- Cloudflare Pages built the feature-branch preview successfully. The console is exposed only on the preview URL; production has not received these post-merge follow-up commits.
- CORS is limited to the Jarvis Unified Portal Pages hostname and its preview aliases, plus any exact origins explicitly configured through `JAEO_ALLOWED_ORIGINS`.
- Automated CI for the newest portal-console commit is still running. The preceding API/RPC test run passed all 12 workflow steps.
- A live browser sign-up and end-to-end API call have not been performed from this environment because no human QA account/session is available. Do not claim those interactive flows are verified until a human signs in and completes the test.


### Supabase SDK compatibility hardening
- Updated both the Edge Function and browser console to the current pinned `@supabase/supabase-js@2.119.2`, so the new publishable/secret key model is supported without relying on the legacy `anon`/`service_role` keys.
- Redeployed `jaeo-operator` to isolated QA as version 4 with `verify_jwt=true`.
