# Cloudflare domain and hosting plan

## User-approved direction and budget

- Brand domain preference: `jarvisunified.com`.
- Hosting/domain budget preference: free; do not purchase or start paid services.
- Cloudflare Registrar's authoritative check returned `registrable: true` for `jarvisunified.com`, with a quoted registration and renewal price of USD 11.17 each. This is a paid registration, so no purchase was made.
- The connected Cloudflare account currently has no DNS zone for `jarvisunified.com`.
- Until the domain is acquired, use a Cloudflare-provided `pages.dev` address for a new, safe public landing page. A `pages.dev` address is free hosting, not ownership of the `.com` domain.

## Existing Cloudflare Pages resource — verified

The connected Cloudflare account contains one Pages project:

| Field | Verified value |
|---|---|
| Project | `jarvis-control-panel` |
| Default hostname | `jarvis-control-panel.pages.dev` |
| Git repository | `beeniko33-dotcom/jarvis-unified` |
| Production branch | `main` |
| Output directory | `apps/control_panel` |
| Build command | Empty (static files are published directly) |
| Current production source | `main` at the Forex-only refocus commit |
| Feature-branch preview | `feat-jarvis-four-pillar-arch.jarvis-control-panel.pages.dev` |
| Latest feature-branch preview result | Cloudflare reported build and deploy stages successful |

### Critical legacy UI warning

The existing `apps/control_panel/index.html` is a legacy trading workspace. Source inspection found paper-environment labels, a demo portfolio/paper-trading page, simulated orders and positions, and copy describing paper-trading operations. This does not meet the agreed Forex Signal Intelligence boundary.

Therefore:

- Do not present `jarvis-control-panel.pages.dev` or its branch preview as the new Forex Signal Intelligence product.
- Do not attach `jarvisunified.com` or any public product hostname to this legacy project.
- Do not re-enable its old Worker, paper execution, broker or cron paths.
- Before any public product launch, replace or retire this legacy frontend through a reviewed change and verify that the deployed output contains no execution UI or endpoints. If it must remain temporarily for internal recovery, protect it with an explicit access policy and verify that policy from an unauthenticated session.
- A successful Pages build only confirms static deployment; it does not establish product correctness, security, or release readiness.

A separate static portal project has now been created:

| Field | Value |
|---|---|
| Project | `jarvis-unified-portal` |
| Free hostname | `jarvis-unified-portal.pages.dev` |
| Repository path | `apps/portal` |
| Build command | None (static HTML) |
| Production branch | `main` |
| Feature branch | `feat/jarvis-four-pillar-architecture` (preview only) |
| Custom domain | None |

The portal source is intentionally informational and labels product availability honestly. Its initial feature-branch deployment is being processed; do not call it live until Cloudflare reports the deploy stage successful and the public page is checked in a browser. The project is separate from the legacy control panel.

## Target public URL structure

Once a new, safe landing page and each app are independently implemented and verified, use:

| Purpose | Recommended hostname | Release condition |
|---|---|---|
| Main brand / product directory | `jarvisunified.com` | Domain owned and added to Cloudflare |
| Forex Signal Intelligence | `signals.jarvisunified.com` | Read-only data and forecast UI verified |
| Marketplace | `marketplace.jarvisunified.com` | Listings, provenance and disclosures verified |
| Career | `career.jarvisunified.com` | Private document access and user-approval flow verified |
| JAEO | `jaeo.jarvisunified.com` | Private operator authentication, authorization, audit and approval tests pass |
| API gateway | `api.jarvisunified.com` | Versioned API contracts, server-side scopes and abuse controls verified |
| Status page | `status.jarvisunified.com` | Monitoring and incident publication are implemented |

Do not create placeholder DNS records or assume any hostname is live.

## Free-first hosting structure

- Keep the existing Pages project isolated as a legacy resource until its replacement/retirement is reviewed.
- Create a separate Cloudflare Pages project for the new public portal only after its source directory contains a safe, complete static frontend. Use a descriptive project name such as `jarvis-unified-portal`; do not repoint the existing legacy project.
- Use separate Pages projects for independently released applications when their frontends are ready. Use free `pages.dev` addresses for previews and early validation.
- Prefer Cloudflare Workers with Workers Static Assets for new full-stack edge applications where server-side logic is actually required. Do not create a Worker merely to host a static page.
- Keep durable application data in a deliberately selected database. Do not point new code at the paused Supabase projects.
- Do not restore the deleted legacy control/MCP Workers or their one-minute Cron configuration.
- Keep JAEO's admin console private. Cloudflare Access may provide an outer identity gate, but it does not replace application-level authorization.
- Separate production, staging and preview; never copy production secrets into previews.
- Apply strict TLS, security headers, rate limits, WAF rules, bot protections, CORS allowlists and CSRF protections where applicable.
- Use server-side authorization, short-lived sessions, least privilege and auditable approval records.
- Keep the first release within the user's free-only budget. Any paid resource or usage-based service requires explicit cost review and approval first.

## Staged hostname rollout

1. **Free development:** build and test on a new project-specific `pages.dev` address. Keep the legacy project separate.
2. **Safe public portal:** publish the new root landing page only after content, navigation, privacy, terms, support and security checks pass.
3. **Product apps:** add Signals, Marketplace and Career hostnames only after each app's independent release gates pass.
4. **JAEO:** keep the operator console private until authentication, authorization, approvals, audit and human handoff are verified.
5. **API and status:** expose these only after their contracts and monitoring are ready.
6. **Custom domain:** only after the user chooses to pay for registration or confirms that they already own the domain; then add the zone, configure DNS and verify TLS.

## Release gates

- No Forex order, paper-trading or broker-execution UI/API may be exposed.
- Do not deploy the existing root Wrangler configuration as-is: it still references a deleted Worker, a paused Supabase project and a one-minute Cron.
- Do not claim a feature is live based only on a build or a deployment record.
- Verify public and unauthenticated access behavior, DNS, TLS, application authorization, secrets, backups/recovery and cost limits.
- No domain has been purchased and no `jarvisunified.com` DNS zone or custom hostname has been configured.
