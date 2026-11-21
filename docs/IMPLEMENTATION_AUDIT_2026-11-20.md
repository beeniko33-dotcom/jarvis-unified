# Repository implementation audit — 2026-11-20

## Scope and confidence

This is a source-level first-pass audit of the default branch `main` at commit `0a6f4886f174799b066d338da9c2065ff1f3e94a`, supplemented by the four-pillar architecture branch and a read-only inspection of the connected Cloudflare account. It is not a complete clone-based test run, security review, or deployment verification. Findings below are limited to files and resources inspected and must be revalidated before implementation.

## Confirmed findings

### Product architecture drift
- The default-branch README identifies Jarvis Unified as Forex-only, despite the agreed ecosystem containing Forex Signal Intelligence, Marketplace, Career and JAEO.
- The four-pillar architecture is documented on `feat/jarvis-four-pillar-architecture` and proposed in draft PR #212.
- The repository currently has no root `package.json`; the inspected root project is Python-based (`pyproject.toml`, `main.py`).

### Critical Forex boundary conflict
- `pyproject.toml` still describes the package as a paper-first trading platform and includes trading-related modules in its package configuration.
- `main.py` imports `PaperBroker`, `ExecutionService`, order models and risk controls; it includes a paper demo that submits and closes orders.
- The existing static UI at `apps/control_panel/index.html` is explicitly a trading workspace. It contains paper-environment labels, a demo portfolio/paper-trading page, simulated orders and positions, and copy promoting paper-trading operations.
- This conflicts with the agreed Forex Signal Intelligence product boundary (read-only research, no paper/live/demo execution).
- Do not expose or deploy the legacy runtime or legacy UI as the Forex product. Do not simply delete modules before tracing imports, tests, workflows, schemas and historical dependencies. First isolate them from product routing and then remove or archive them only after a verified migration and regression plan.

### Infrastructure and deployment drift
- Root `wrangler.jsonc` and `cloudflare/wrangler.jsonc` still describe `jarvis-control-worker`, include a one-minute Cron Trigger and reference the former production Supabase URL.
- The related Cloudflare Workers were removed in the recent infrastructure cleanup. Therefore these files and associated workflows/docs are stale deployment artefacts and must not be redeployed unchanged.
- Supabase production and prototype projects were paused, not permanently deleted. Their previous URLs/configuration must not be treated as active services.
- The connected Cloudflare account has a legacy Pages project, `jarvis-control-panel`, at `jarvis-control-panel.pages.dev`. It is linked to this repository, builds directly from `apps/control_panel`, and uses `main` as its production branch. A separate `jarvis-unified-portal` Pages project has been created for `apps/portal`, with `main` as production branch and feature-branch previews enabled.
- Cloudflare reported a successful static deployment of the first `jarvis-unified-portal` snapshot at `https://d12898ac.jarvis-unified-portal.pages.dev`. The latest copy-corrected preview at `https://02b6723e.jarvis-unified-portal.pages.dev` has successful Cloudflare build and deploy stages; browser rendering remains unverified. The legacy `jarvis-control-panel` feature preview is also reported successful, but remains the old trading UI and is not a safe product launch.
- The existing production Pages deployment is based on the `main` branch. Do not attach the proposed `jarvisunified.com` domain or product subdomains to this legacy project.
- Cloudflare's authoritative registrar check returned `jarvisunified.com` as registrable at USD 11.17 registration and USD 11.17 renewal. The user chose a free-only domain preference, so no purchase was made. No `jarvisunified.com` zone exists in the connected Cloudflare account.
- The Cloudflare account cleanup removed the identified Jarvis Workers; it did not authorize deleting unrelated account resources or the entire Cloudflare account.

### CI and verification
- The inspected CI workflow still includes root Wrangler preview validation and a smoke test against a legacy Worker preview URL, in addition to the forecast, regression, JAEO, feed and container tests.
- The `pull_request` workflow filter includes `main`, so a PR targeting `main` is eligible to trigger CI. The `push` filter does not include `feat/jarvis-four-pillar-architecture`, so direct pushes to that branch do not trigger the push workflow.
- GitHub Actions CI run #44874786174 completed successfully on the architecture PR head during the 2026-11-20 follow-up verification. Its single `test` job passed all steps: pinned dependency installation and `pip check`, public portal boundary check, Forex forecast tests, full repository regression suite, JAEO supervised-operations policy tests, Deriv read-only feed tests, foundation diagnostic, Docker build/smoke test, and container cleanup. This validates the tested commit only; it does not constitute a security review, app-level end-to-end validation, or production release. The Cloudflare Pages preview success is not a substitute for GitHub Actions tests.
- The existing Worker smoke test expects a paper-mode health response from a legacy Worker URL. This is incompatible with the agreed Forex product boundary and must be retired or replaced only after the workflow and all consumers are reviewed.

## Priority implementation plan

### P0 — contain unsafe and stale paths
1. Keep the existing legacy control panel separate from all new product hostnames; review whether it should be protected or retired before public launch.
2. Add a product-level routing boundary that exposes only the Forex research forecast service, not the legacy trading runtime.
3. Remove legacy paper/demo execution from the Forex-facing entrypoint and feature registry only after tests and dependency tracing establish a safe separation.
4. Disable stale Worker preview/deploy steps and Cron declarations until the replacement architecture and infrastructure are intentionally provisioned.
5. Replace stale operational docs with truthful status: Workers deleted; Supabase projects paused; no active JAEO runtime deployment verified.
6. Preserve CI coverage for the architecture branch while replacing obsolete Worker smoke tests with meaningful product-boundary and security checks.

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
- Cloudflare Pages: one legacy control-panel project exists and must not be reused; a separate free-first `jarvis-unified-portal` project has been created. Cloudflare reported the first static portal snapshot deployed successfully; the latest copy-corrected preview has successful Cloudflare build/deploy stages, while browser verification is pending.
- Cloudflare Workers: identified Jarvis Workers removed in prior cleanup.
- Supabase: projects paused; permanent deletion not verified.
- `jarvisunified.com`: available at a paid price in the latest registrar check; not purchased and not configured.
- Production release: not approved or verified.
- Forex execution: prohibited by product requirements; legacy source and UI still require isolation/removal work.


## Follow-up verification — 2026-11-20

- Draft PR #212 remains open, unmerged and mergeable.
- Latest observed PR head at this check: `6c05564467854fa6b82927458b0c022106dc273b`.
- GitHub Actions run #44874786174 completed with conclusion `success`; the `test` job and every reported step completed successfully.
- The follow-up source review reconfirmed that `main.py` still imports `PaperBroker`, `ExecutionService`, order models and risk controls, and still exposes a paper-demo command. `core/feature_registry.py` still reports paper execution as enabled. The legacy `apps/control_panel/index.html` remains a trading workspace. These are unresolved migration blockers, not part of the new static portal.
- The public portal is static and correctly labels Marketplace and Career as planned and JAEO as architecture in progress. No complete product application or active JAEO service was verified.
- No new production deployment, domain purchase, Supabase restoration, or secret provisioning was performed during this follow-up.
