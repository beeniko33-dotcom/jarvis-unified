# Repository implementation audit — 2026-11-20

## Scope and confidence

This is a source-level first-pass audit of the default branch `main` at commit `0a6f4886f174799b066d338da9c2065ff1f3e94a`, supplemented by the four-pillar architecture branch. It is not a complete clone-based test run, security review, or deployment verification. Findings below are limited to files inspected and must be revalidated against the current branch before implementation.

## Confirmed findings

### Product architecture drift
- The default-branch README identifies Jarvis Unified as Forex-only, despite the agreed ecosystem containing Forex Signal Intelligence, Marketplace, Career and JAEO.
- The four-pillar architecture is now documented on `feat/jarvis-four-pillar-architecture` and proposed in draft PR #212.
- The repository currently has no root `package.json`; the inspected root project is Python-based (`pyproject.toml`, `main.py`).

### Critical Forex boundary conflict
- `pyproject.toml` still describes the package as a paper-first trading platform and includes trading-related modules in its package configuration.
- `main.py` imports `PaperBroker`, `ExecutionService`, order models and risk controls; it includes a paper demo that submits and closes orders.
- This conflicts with the agreed Forex Signal Intelligence product boundary (read-only research, no paper/live/demo execution).
- Do not expose or deploy the legacy runtime as the Forex product. Do not simply delete modules before tracing imports, tests, workflows, schemas and historical dependencies. First isolate it from product routing and then remove or archive it only after a verified migration and regression plan.

### Infrastructure and deployment drift
- Root `wrangler.jsonc` and `cloudflare/wrangler.jsonc` still describe `jarvis-control-worker`, include a one-minute Cron Trigger and reference the former production Supabase URL.
- The related Cloudflare Workers were removed in the recent infrastructure cleanup. Therefore these files and associated workflows/docs are stale deployment artefacts and must not be redeployed unchanged.
- Supabase production and prototype projects were paused, not permanently deleted. Their previous URLs/configuration must not be treated as active services.
- Documentation still describes former Workers, Supabase queues, paper execution and operator controls as if provisioned. Those statements require correction before any deployment work.
- The Cloudflare account cleanup removed the identified Jarvis Workers; it did not authorize deleting unrelated account resources or the entire Cloudflare account.

### CI and verification
- The inspected CI workflow still includes Cloudflare Worker preview checks and a Docker smoke test against the legacy runtime.
- CI branch filters do not yet include `feat/jarvis-four-pillar-architecture` or the current architecture PR branch, so PR checks may not run automatically.
- No local test execution was performed as part of this source-only audit. Existing historical green runs do not validate the current branch.

## Priority implementation plan

### P0 — contain unsafe and stale paths
1. Add a product-level routing boundary that exposes only the Forex research forecast service, not the legacy trading runtime.
2. Remove legacy paper/demo execution from the Forex-facing entrypoint and feature registry only after tests and dependency tracing establish a safe separation.
3. Disable stale Worker preview/deploy steps and Cron declarations until the replacement architecture and infrastructure are intentionally provisioned.
4. Replace stale operational docs with truthful status: Workers deleted; Supabase projects paused; no active JAEO runtime deployment verified.
5. Add CI coverage for the architecture branch and ensure CI tests do not require removed production resources or secrets.

### P1 — establish application foundations
1. Define independent app boundaries for `forex`, `marketplace`, and `career`.
2. Define shared identity contracts without implicit cross-app trust.
3. Define server-enforced authorization scopes, audit event schema, approval records and notification contracts.
4. Create JAEO task lifecycle and human-support handoff contracts. Keep JAEO supervised; no self-approval or privilege escalation.
5. Add API contracts and integration tests before connecting external providers.

### P2 — implement each product
- Forex: verified read-only feeds, provenance/freshness validation, explainable forecasts, signal history and alerts.
- Marketplace: curated listings, provenance and freshness, search/filter/saved items, affiliate disclosures and moderation.
- Career: jobs, CV tools, skills, application tracking and explicit review before external submission.
- JAEO: authenticated intake, policy routing, approvals, human support, append-only audit and status dashboard.

### P3 — release readiness
- Run unit, integration, authorization, abuse, privacy, accessibility and end-to-end tests.
- Verify deployment configuration, DNS, TLS, secrets, backup/recovery and cost limits.
- Release each app independently behind reviewed deployment gates.
- Do not claim a feature is live until a live endpoint and its behavior are independently verified.

## Current state summary

- Architecture docs: proposed on a draft PR.
- Product applications: not yet verified as complete.
- JAEO runtime: not verified as deployed.
- Cloudflare Workers: identified Jarvis Workers removed in prior cleanup.
- Supabase: projects paused; permanent deletion not verified.
- Production release: not approved or verified.
- Forex execution: prohibited by product requirements; legacy source still requires isolation/removal work.
