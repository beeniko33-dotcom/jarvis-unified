# Jarvis Unified redesign blueprint

## Approved product direction

- Forex-first research, analytics and risk management.
- Selected Forex provider: Deriv MT5, subject to account/instrument eligibility and terminal bridge setup.
- Gate.io remains a separate read-only crypto spot integration.
- Marketplace: hybrid discovery directory first, expandable to seller/buyer transactions.
- JAEO: natural-language command centre and supervised operations orchestrator.
- Notifications: website/PWA push notifications with user opt-in.
- Authorized engineering scope: feature branches, code changes, tests and pull requests. No production deployment, live trades, paid provisioning, production resource mutations or irreversible actions.

## Deriv integration reality

Deriv MT5 is a plausible provider for a Nigeria-based user: Nigeria appears in Deriv's published country list for MT5. This is not a guarantee of account acceptance, instrument availability, or regulatory suitability; the user's own account and terms govern.

Important technical distinction: Deriv's current public REST/WebSocket API documents options contract workflows. Deriv's MT5 API documentation covers account management and payments, and explicitly states that MT5 trading is not supported through those APIs; trading is performed in the MT5 application. Therefore Jarvis must not treat a Deriv API token as an MT5 order API.

The intended Forex path is:
1. User opens/maintains an eligible Deriv MT5 account and verifies the desired FX symbols in their own MT5 terminal.
2. A dedicated MT5 Expert Advisor (EA) publishes authenticated, timestamped quotes/account state to a Jarvis bridge.
3. Jarvis validates freshness, symbol mapping, account identity, permissions and risk limits.
4. Initially, Jarvis emits research signals and demo-only trade intents; any future terminal execution is separately gated and approved.
5. The EA reports acknowledgements, fills, rejects, position changes and heartbeats for reconciliation.

The MT5 bridge must use TLS, per-install credentials, signed requests, nonce/timestamp replay protection, strict account binding, allowlisted symbols, bounded request sizes, idempotency keys, rate limits, and a kill-switch check before every order. Secrets must never be placed in source code or chat. No bridge endpoint or EA is considered operational until deployed and end-to-end tested.

## Product architecture

### 1. Forex intelligence
- Keep FX symbols (e.g. EUR/USD, GBP/USD, USD/JPY) separate from crypto symbols.
- Normalize bid/ask quotes, candles, timestamps, spread, trading sessions and provenance.
- Research: multi-timeframe trend, volatility, momentum, support/resistance candidates and economic-calendar context.
- Risk: position sizing, per-trade/daily loss caps, exposure and correlation checks, spread/slippage limits, stale-data rejection, stop-loss/take-profit validation and kill-switch enforcement.
- A signal is not an order. No live execution path is enabled.

### 2. JAEO command centre
Natural-language requests become typed tasks with identity, scope, role, action, resource, risk class, idempotency key and status. JAEO reports capability boundaries, progress and auditable results.

Specialist roles: Orchestrator, Forex Research, Risk, Market Data, Jobs Discovery, Affiliate Research, Marketplace Operations, Security, QA and Release.

Low-risk inspection, research, tests and authorized branch/PR work can be automated. Human approval remains mandatory for trades, external submissions, money movement, credentials, destructive actions, deployments and paid resources. Production resources remain read-only. Self-improvement means bounded monitoring and reviewed recommendations, not self-modifying code or consciousness.

### 3. Opportunity discovery
Prioritize official employer career pages, ATS feeds, public APIs/RSS, affiliate programme pages, remote-work listings, AI tools and digital products. Respect terms, robots directives, rate limits and access controls; do not bypass authentication or anti-bot protections.

Normalize source URL, title, description, category, work mode, country eligibility, compensation, skills, dates, source verification and deduplication fingerprint. Preserve attribution. Flag suspicious domains, impersonation, upfront fees, unrealistic pay and mismatched contact domains. Draft applications only; submit only with per-application approval.

### 4. Hybrid marketplace
Phase one: remote jobs/freelance work, affiliate programmes, AI tools and digital products. Include search, filters, country eligibility, source attribution, freshness, bookmarks, alerts, reports, affiliate disclosures and clearly labelled sponsored listings.

Phase two may add seller profiles, user-submitted listings, downloads and services. Payments, KYC, refunds, taxes, disputes, escrow and payouts require separate legal/security/payment design and approval.

### 5. Notifications
PWA notifications for Forex watch alerts, risk/system incidents, matching jobs, affiliate changes, marketplace updates and JAEO task completion. Require explicit opt-in, category controls, unsubscribe, quiet hours, deduplication and expiry. iOS web push requires Home Screen installation and permission. A verified backend subscription store and scheduler are required.

## Security, data and budget
- Keep credentials in provider secret stores; never in chat or browser bundles.
- Separate market observations, user profiles, tasks/approvals, financial account state and marketplace records.
- RLS and service-role-only access for private operational tables.
- Treat scraped content as untrusted data, never as JAEO instructions.
- Immutable audit records, least privilege, idempotency, rate limits and input/output validation.
- Free-first target: at most ₦5,000/month. No paid resources without explicit cost review and approval.

## Implementation sequence
1. Broker domain separation and Deriv MT5 selection metadata (catalogue foundation).
2. Design and implement authenticated MT5 EA bridge and read-only FX feed.
3. Add FX instruments, quote normalization, research and risk engine.
4. Build JAEO typed command/task API with approval-bound action routing.
5. Add compliant opportunity source registry, fetchers, normalization, deduplication and scam flags.
6. Build hybrid directory and moderation.
7. Add PWA notification preferences, subscriptions and delivery worker.
8. Test in isolated environments; add demo-only terminal lifecycle after explicit authorization.
9. Consider production rollout only after a separate approval and verified budget, security, rollback and operating evidence.

## Current status
This is an architecture and broker-catalog foundation only. It does not connect a Deriv account, fetch Deriv MT5 quotes, deploy an EA/bridge, create a JAEO runtime, run a scraper, deliver push notifications, accept marketplace payments or deploy production. Existing production controls and paper-only safeguards remain unchanged.
