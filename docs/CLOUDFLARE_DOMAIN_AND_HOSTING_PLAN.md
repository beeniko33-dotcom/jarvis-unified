# Cloudflare domain and hosting plan

## Recommended public URL structure

Use one memorable root domain for the Jarvis brand and subdomains for the independently scoped applications:

| Purpose | Recommended hostname | Notes |
|---|---|---|
| Main brand / product directory | `jarvisunified.com` | Public landing page explaining the ecosystem |
| Forex Signal Intelligence | `signals.jarvisunified.com` | Research-only market dashboard |
| Marketplace | `marketplace.jarvisunified.com` | Listings, AI tools and digital products |
| Career | `career.jarvisunified.com` | Jobs, CV tools and application tracking |
| JAEO | `jaeo.jarvisunified.com` | Authenticated command and operations console; never public admin access |
| API gateway | `api.jarvisunified.com` | Versioned APIs only; strict auth, rate limits and app scopes |
| Status page | `status.jarvisunified.com` | Public uptime/incident notices; no sensitive system details |

These are naming recommendations only. Domain ownership, availability, DNS records, hosting and TLS are not verified or provisioned.

## Domain alternatives

If `jarvisunified.com` is unavailable or too expensive, check these in order:
- `jarvisunified.app`
- `jarvisunified.io`
- `jarvisunified.dev` (best for development, less ideal as the main consumer brand)
- `getjarvisunified.com`
- `usejarvis.ai`

Do not assume any name is available. Check registration price and renewal price before purchasing. Prefer one root domain over several unrelated domains to build brand trust and simplify DNS.

## Cloudflare hosting layout

- Put the public landing page and each web frontend on Cloudflare Pages or a supported static hosting deployment, with separate projects/environments per app.
- Use Cloudflare DNS for the root and subdomains after the domain is registered and added to the account.
- Use Cloudflare Workers only for small, stateless API gateway/edge tasks where the runtime and security model are tested. Do not restore the deleted legacy control/MCP workers or their one-minute Cron configuration.
- Keep durable application data in a deliberately selected database service. Do not point new code at the paused Supabase projects.
- Keep JAEO's admin console behind authentication and strong authorization. Consider Cloudflare Access for a private operator-only surface, but do not treat Access as a replacement for application-level authorization.
- Separate production, staging and preview hostnames; use no production secrets in preview environments.
- Add DNSSEC where supported, strict TLS, security headers, rate limiting, WAF rules and bot protections after domain setup.
- Keep API hostnames separate from frontend hosts and enforce CORS allowlists, CSRF protection where applicable, short-lived sessions and server-side authorization.
- Display clear privacy, terms, affiliate disclosures and contact/support routes on public apps.

## Staged hostname rollout

1. Development: `dev.jarvisunified.com` and app-specific preview URLs.
2. Public launch: `jarvisunified.com`, `signals.`, `marketplace.`, `career.`.
3. JAEO private operator console: `jaeo.` only after authentication, authorization, audit and approval flows pass security tests.
4. API: `api.` only when versioned API contracts and access scopes are ready.
5. Status: `status.` when monitoring and incident publication are implemented.

## Important release gates

- Do not publish JAEO admin routes publicly before role and approval controls are verified.
- Do not expose secrets, database admin endpoints, internal logs, customer records or control-plane actions in browser code.
- Do not deploy the existing root Wrangler configuration as-is: it still references a deleted Worker, a paused Supabase project and a one-minute Cron.
- Domain suggestions are not a claim of registration or availability. No domain has been purchased or DNS changed by this document.
