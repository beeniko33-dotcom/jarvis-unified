# Jarvis Unified public portal

This is a static, informational landing page for the four-pillar Jarvis Unified ecosystem.

## Scope and safety

- Describes the target Forex Signal Intelligence, Marketplace, Career and JAEO products.
- Clearly labels each product's implementation status.
- Forex is read-only research only. This portal contains no trading UI, broker integration, order placement or execution path.
- Marketplace and Career are not represented as live services until separately implemented and verified.
- JAEO is a supervised governance layer; the portal does not expose an operator console or admin actions.
- No backend, secrets, user accounts or personal data are required to serve this static page.

## Cloudflare Pages

- Project: `jarvis-unified-portal`
- Output directory: `apps/portal`
- Build command: none (static HTML)
- Intended initial free hostname: `jarvis-unified-portal.pages.dev`
- The connected Pages project is currently configured to deploy the architecture feature branch. This is an early public preview, not a production release on a custom domain.
