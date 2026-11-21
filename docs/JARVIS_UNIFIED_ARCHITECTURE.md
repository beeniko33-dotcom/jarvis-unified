# Jarvis Unified — Product Architecture

## Product vision

Jarvis Unified is one branded ecosystem made of three independently deployable applications and one shared supervised intelligence/governance layer:

1. Forex Signal Intelligence
2. Marketplace
3. Career
4. JAEO (Jarvis AI Executive Operator)

The applications share identity, navigation conventions, notification preferences and governed services where appropriate. They retain separate product boundaries, authorization scopes, data ownership and deployment controls.

## 1. Forex Signal Intelligence

Purpose: read-only foreign-exchange market research and directional forecasts.

Planned capabilities:
- Ingest market observations with provider, instrument, timeframe, observed-at timestamp, received-at timestamp, freshness and quality metadata.
- Reject stale, malformed, future-dated or incomplete observations.
- Produce explainable bullish, bearish or neutral forecasts across supported timeframes.
- Show evidence, trend/momentum context, confidence/strength methodology and data-quality status.
- Maintain forecast history, signal-change records, watchlists and configurable alerts.
- Evaluate historical forecast quality only when sufficient verified observations exist; distinguish measured calibration from heuristic scores.

Hard boundary:
- No live, demo or paper trading.
- No order placement, execution adapters, broker order APIs, positions, balances, leverage, sizing or trade lifecycle.
- No execution-style entry/stop/target instructions.
- Gate.io is a separate crypto integration decision and must not be represented as a conventional-FX feed or execution route.
- Forex screens and APIs must not expose legacy execution modules.

## 2. Marketplace

A separate application under the Jarvis brand.

Initial hybrid scope:
- Curated job and freelance opportunities.
- Affiliate offers and partner opportunities with clear disclosure.
- AI tools directory and useful software discovery.
- Digital products and downloadable resources.
- Search, categories, filters, saved items and notifications.
- Later expansion: buyer/seller accounts, seller onboarding, listings, orders, reviews and marketplace administration.

Listings must carry provenance, last-checked timestamps, eligibility/location details where known, and clear sponsored/affiliate disclosures. Collection must respect source terms, robots rules, rate limits and applicable privacy requirements. Do not imply a partnership or live inventory without verification.

## 3. Career

A separate career application, not merely a Marketplace category.

Planned capabilities:
- Job discovery, search, filters, saved jobs and alerts.
- Career guidance and skill-development resources.
- CV/resume creation, editing and role-tailoring tools.
- Application tracking and reminders.
- Optional application assistance with explicit user review and approval before any submission.
- Clear source links and freshness metadata for opportunities.

Career data and documents must be private to the user and protected by least-privilege access.

## 4. JAEO — supervised command and governance layer

JAEO is the shared natural-language command, orchestration, support and audit layer. It coordinates permitted tasks across the three applications; it does not bypass their boundaries.

Planned capabilities:
- Authenticated command intake and intent classification.
- Route requests to Forex research, Marketplace discovery, Career workflows or shared services.
- Task state, ownership, retries, status reporting and notification delivery.
- Approval queue for consequential actions; applications and external submissions require explicit user approval.
- Human administrator/support handoff, case history and service-quality monitoring.
- Append-only audit events for actor, action, target, decision, timestamp and outcome.
- Role-based administration, scoped service identities and policy enforcement.
- System health and integration monitoring without exposing secrets.

Governance requirements:
- Deny by default; enforce authorization on the server, not only in the UI.
- Separate user, support-agent, administrator and service permissions.
- Record approvals and bind each approval to a specific action and payload.
- Expire or invalidate approvals when the action changes.
- Never treat a natural-language request, task status or model output as authorization.
- No automatic privilege elevation or self-approval by JAEO.
- No production action until security, tests, release review and required human approvals pass.

## Cross-application platform principles

- Independent application boundaries with shared brand and consistent navigation.
- Shared identity only through explicit, tested SSO/session design; no implicit trust between apps.
- Separate data ownership and authorization scopes.
- Centralized, auditable notifications and task orchestration.
- Data provenance, timestamps and freshness for external information.
- Privacy by default, secret management, rate limiting and abuse protection.
- Free-first operating posture; avoid introducing paid dependencies without explicit review.
- Preserve recoverability of the legacy prototype outside active application routing and deployment.

## Delivery sequence

1. Inventory the repository, branches, workflows, services, schemas and existing tests.
2. Establish the four-pillar architecture and app/service boundaries.
3. Audit and isolate legacy trading/paper-execution code from the Forex product; remove only after dependency and regression tests prove safe.
4. Define shared identity, authorization, audit-event and approval contracts.
5. Build JAEO authenticated intake, task routing, approval records, human support handoff and audit trail.
6. Deliver Forex data-quality and research forecast capabilities without execution paths.
7. Deliver Marketplace discovery and provenance-aware listings.
8. Deliver Career workflows and user-private document handling.
9. Add cross-app integration, security, accessibility and end-to-end tests.
10. Verify release artifacts and deployment configuration before any release decision.

## Current status and safety

This document records the agreed target architecture; it is not evidence that every capability is implemented or deployed. The repository must be audited before implementation claims are made. This architecture update does not authorize production deployment, merging, live services, trading, paper execution, destructive cleanup of unrelated resources, or bypassing JAEO approval gates.
