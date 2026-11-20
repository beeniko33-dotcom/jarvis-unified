# Jarvis Unified redesign blueprint

## Approved product direction

This blueprint records the operator's selections on 2026-11-20:

- Primary trading product: Forex-focused research, analytics and risk management.
- Requested broker: Gate.io, retained as a separate crypto spot integration.
- Marketplace: hybrid discovery directory first, extensible to seller/buyer transactions later.
- JAEO: natural-language command centre and supervised operations orchestrator.
- Notifications: website/PWA push notifications for user-approved alert categories.
- Engineering authorization: feature branches, code changes, tests and pull requests are authorized. Production deployments, live trades, paid provisioning, production database/Worker mutations and other irreversible actions are not included.

## Critical broker-domain distinction

Gate.io is a crypto exchange, not a conventional Forex broker. The current Jarvis Gate.io path is read-only public market observation/attestation. It must not be represented as Forex market data, authenticated account access, or order execution.

The broker catalog now models market domains explicitly and rejects Gate.io-to-Forex routing. A future Forex adapter requires a named provider that actually supports the requested FX instruments and a verified account/API contract. MT5 is a platform/protocol ecosystem, not a broker by itself. Before selecting a provider, verify Nigerian account eligibility, regulatory standing, supported FX symbols, demo environment, API/EA access, spreads/commissions, financing, and withdrawal terms. No broker is presumed selected or connected by this blueprint.

## Product architecture

### 1. Forex intelligence

- FX-specific instrument catalogue (for example EUR/USD, GBP/USD and USD/JPY) kept separate from crypto symbols.
- Provider adapters expose normalized quotes/candles, timestamps, bid/ask, spread, session and provenance.
- Research layer: multi-timeframe trend, volatility, momentum, support/resistance candidates, economic-calendar context and explainable signal confidence.
- Central risk service: position sizing, per-trade and daily loss limits, max concurrent exposure, correlation checks, spread/slippage limits, stale-data rejection, stop-loss/take-profit validation and kill-switch enforcement.
- Strategy output is a research signal, not an order. Broker execution remains unavailable until a separately reviewed provider adapter, test evidence and explicit live-trading authorization exist.
- Gate.io stays in a distinct crypto domain; its market data cannot silently feed Forex strategy calculations.

### 2. JAEO command centre

Natural-language requests are parsed into typed tasks with an owner, scope, agent role, requested action, resource, idempotency key, risk class and current status. JAEO should report what it can and cannot do, show progress, and retain an auditable result.

Initial specialist roles: Orchestrator, Forex Research, Risk, Market Data, Jobs Discovery, Affiliate Research, Marketplace Operations, Security, QA and Release.

JAEO can autonomously perform low-risk inspection, tests, research and permitted branch/PR workflows. Human approval remains mandatory for external submissions, money movement, trades, credential changes, destructive actions, schema changes, deployments and paid resources. Production resources remain read-only to JAEO. A natural-language interface is not permission to execute arbitrary commands or bypass policy.

Self-improvement means bounded monitoring, metrics, feedback and reviewed recommendations. It does not mean self-modifying code, changing permissions or becoming conscious.

### 3. Opportunity discovery

Prioritize public, permitted sources:
- Employer career pages and official ATS feeds.
- Public RSS/Atom feeds and job APIs.
- Affiliate programme directories and official partner pages.
- Public remote-work and freelance opportunity listings.
- AI tools and digital product catalogues.

Respect source terms, robots directives, rate limits and access controls. Do not bypass login walls, CAPTCHAs, anti-bot controls or paywalls. Prefer official APIs/feeds over scraping.

Normalize each listing with source URL, source identity, title, description, category, remote/work mode, country eligibility, compensation, skills, posted/expiry dates, last-seen time, deduplication fingerprint and verification status. Preserve attribution and provide an outbound source link.

Scam screening should flag (not silently assert) suspicious domains, impersonation, upfront-fee requests, unrealistic compensation, mismatched contact domains and copied descriptions. Users can report listings. Applications may be drafted for the user; submission requires explicit per-application approval.

### 4. Hybrid marketplace

Phase one is a discovery directory containing:
- Remote jobs and freelance work.
- Affiliate programmes and partner offers.
- AI tools and useful online services.
- Digital products and learning resources.

Phase-one capabilities: search, category filters, country/eligibility filters, source attribution, freshness indicators, save/bookmark, alerts, outbound links, listing reports, affiliate disclosures and optional sponsored placements with clear labels.

Phase two may add user-submitted listings, seller profiles, digital downloads and service offers. Payments, seller verification/KYC, refunds, tax handling, disputes, escrow and payouts require a separate legal, security and payment-provider design before activation. Do not collect payment or imply escrow exists in the directory phase.

### 5. Website and mobile notifications

Use the existing installable web app/PWA as the delivery surface. Notification categories: Forex watch alerts, risk/system incidents, new matching jobs, affiliate programme changes, marketplace updates and JAEO task completion.

Requirements: explicit opt-in, per-category preferences, unsubscribe, quiet hours/digest, expiry and deduplication. iOS web push requires the site to be installed to the Home Screen and notification permission granted. Delivery needs a verified backend subscription store and scheduler/queue; a browser UI alone does not prove push delivery is operational.

## Data and security boundaries

- Keep all credentials in provider secret stores; never accept them in chat or task descriptions.
- Separate public discovery data, private user profiles, task/approval records, market observations and financial account data.
- RLS enabled on exposed tables; private operational tables are service-role-only.
- Treat scraped content and external descriptions as untrusted input. Never allow a listing to become an instruction to JAEO.
- Keep immutable audit events for approvals, commands, broker observations and task results.
- Enforce least privilege, rate limits, idempotency, CSRF protection where applicable, input validation and output sanitization.
- Do not expose service-role credentials in the browser.
- Respect the free-first operating target of at most ₦5,000/month. No paid services or usage commitments without an explicit cost review and approval.

## Implementation sequence

1. Establish explicit market-domain and broker capability separation (implemented in `brokers/catalog.py`).
2. Refactor Forex instruments, feed contracts and strategy outputs without connecting a live execution path.
3. Build the JAEO typed command/task API and approval-bound action router.
4. Add opportunity-source registry, compliant fetchers, normalization, deduplication and scam flags.
5. Build hybrid directory data model, moderation and discovery UI.
6. Add notification preferences, subscription lifecycle and delivery worker.
7. Integrate a named Forex provider only after operator selection and due diligence.
8. Add isolated tests, security review, CI and draft/reviewable PRs.
9. Consider production rollout only after separate explicit authorization and verified budget, security, operational and rollback plans.

## Current status and non-claims

This branch adds the first broker-domain safety layer and this design contract. It does not create a connected Forex broker, market feed, JAEO runtime, scraper schedule, push delivery backend, payment flow or production deployment. Existing production kill switches, entries-paused state, operator controls and paper-only execution checks are not changed.
