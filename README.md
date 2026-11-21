# Jarvis Unified

Jarvis Unified is a single branded ecosystem with three separate applications coordinated by a shared supervised intelligence and governance layer:

- **Forex Signal Intelligence** — read-only FX market research, directional forecasts, signal history and alerts. No live, demo or paper trading and no order execution.
- **Marketplace** — a hybrid discovery marketplace for jobs, affiliate opportunities, AI tools and digital products, with buyer/seller expansion planned separately.
- **Career** — a dedicated career application for job discovery, skills, CV tools, application tracking and user-approved application assistance.
- **JAEO (Jarvis AI Executive Operator)** — the supervised command, task-routing, notification, human-support, approval and audit layer across the ecosystem.

The three applications remain independently scoped. JAEO coordinates them through authenticated, least-privilege interfaces and cannot bypass application permissions or approval requirements.

## Product boundaries

### Forex Signal Intelligence
- Collect market observations with source, timestamp, freshness and quality metadata.
- Analyze multi-timeframe trends and momentum.
- Produce explainable bullish, bearish or neutral research forecasts.
- Maintain forecast history, watchlists and configurable alerts.
- Evaluate historical forecast quality only when verified data is sufficient.

**Strictly research-only:** no live trading, demo trading, paper trading, broker order APIs, execution adapters, positions, balances, leverage, sizing, or trade lifecycle management. Forecasts are not trade instructions. Strength scores are heuristic unless independently calibrated and clearly labelled.

Gate.io, if used, remains a separate crypto integration and must not be conflated with conventional Forex data or execution.

### Marketplace
- Discover curated jobs and freelance opportunities.
- Browse affiliate offers with clear disclosure.
- Discover AI tools and digital products.
- Support search, categories, saved items and freshness-aware alerts.
- Keep buyer/seller expansion as a separately governed phase.

External listings must retain provenance and last-checked metadata. Collection must respect source terms, robots rules, rate limits and privacy requirements.

### Career
- Job search, filters, saved opportunities and alerts.
- Career guidance and skills resources.
- CV/resume creation and role-tailoring tools.
- Application tracking and reminders.
- Application assistance only with explicit user review and approval before submission.

Career documents and personal data require private, least-privilege access.

### JAEO
- Authenticated natural-language command intake and intent routing.
- Governed task orchestration across Forex, Marketplace and Career.
- Explicit approval queues for consequential actions and external submissions.
- Human administrator/customer-support handoff.
- Notifications, system monitoring and task status.
- Auditable records of actor, action, target, approval, timestamp and outcome.

JAEO must deny by default, enforce authorization server-side, separate user/support/admin/service roles, bind approvals to exact actions and payloads, and never self-elevate privileges or treat model output as authorization.

## Development

Run the Forex forecast tests:

    python -m unittest tests.test_forex_forecast -v

Run the full Python test suite:

    python -m unittest discover -s tests -v

For the detailed target architecture, boundaries, governance requirements and delivery sequence, see [docs/JARVIS_UNIFIED_ARCHITECTURE.md](docs/JARVIS_UNIFIED_ARCHITECTURE.md).

## Migration and release status

The repository has been refocused recently toward Forex forecasts. Legacy trading and paper-execution modules may still exist and require a separately tested inventory, isolation and removal; they must never be exposed by the Forex Signal Intelligence product. The older prototype must remain recoverable outside active application routing and deployment.

This README describes the target ecosystem and product boundaries. It does not claim that all four pillars are fully implemented or deployed. Do not merge or deploy until repository-wide implementation, security, integration and release checks have been completed and the required human/JAEO approvals are recorded.
