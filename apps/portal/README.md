# Jarvis Unified public portal

This is a static, informational landing page for the four-pillar Jarvis Unified ecosystem.

## Scope and safety

- Describes the target Forex Signal Intelligence, Marketplace, Career and JAEO products.
- Clearly labels each product's implementation status.
- Forex is read-only research only. This portal contains no trading UI, broker integration, order placement or execution path.
- Marketplace and Career are not represented as live services until separately implemented and verified.
- JAEO is a supervised governance layer; the portal does not expose an operator console or admin actions.
- The landing page itself is static. The linked JAEO QA console uses Supabase Auth and the authenticated `jaeo-operator` Edge Function.
- `jaeo-config.js` contains only the public Supabase publishable key and isolated QA project URL. It is intentionally public; no secret/service-role key may be placed in this directory.
- The JAEO console is for supervised task/approval records only. It does not execute code, deploy, provision resources, merge PRs, trade or perform production actions.
- Other product pillars remain unreleased and must not be presented as live services.

## Cloudflare Pages

- Project: `jarvis-unified-portal`
- Output directory: `apps/portal`
- Build command: none (static HTML)
- Intended initial free hostname: `jarvis-unified-portal.pages.dev`
- The connected Pages project is currently configured to deploy the architecture feature branch. This is an early public preview, not a production release on a custom domain.

Deployment note: this project is intentionally isolated from the legacy control-panel Pages project. The JAEO page calls the isolated QA Supabase Edge Function over HTTPS; no backend secrets are stored in Cloudflare Pages.
