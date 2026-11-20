# Jarvis Autonomous Engineering & Operations (JAEO)

## Configured operating mode

- Autonomy: **supervised**
- Workspace scope: **all** (discoverable connected workspaces; not a claim that every provider is connected)
- Feedback: **both** dashboard and reports
- Trading: paper-only; live trading is permanently denied
- Production operator controls: immutable to JAEO
- Budget: plan for no more than **₦5,000/month**; paid provisioning is blocked until current account billing and total exposure are verified.

## Agent roles

Orchestrator, Engineering, Database, Infrastructure, Security, QA, Research, Release and Audit are policy roles. A role name does not itself create an external model, worker, credential or provider connection. Each provider must be separately connected and verified.

## Permission model

Low-risk inspect, test, branch creation, pull-request creation and paper research can proceed. Code changes, schema changes, secret changes, provisioning, Cron creation, preview deployments and merges require an explicit human approval recorded against the exact action and resource. Production deployments, production operator-control changes and live trading are denied even if an approval is supplied.

Production resource identifiers are denylisted, including the production Supabase project and production control Worker. Never place credentials in task payloads or feedback.

## Task and feedback lifecycle

Tasks use a durable UUID, unique idempotency key, explicit agent role, workspace scope, fixed supervised autonomy and dashboard-plus-report feedback. Feedback records capture status, inspected/changed resources, tests, deployment state, errors, evidence URLs and recommendations. Feedback is append-only.

## Integration truth

Read-only access is verified for the GitHub repository, the production and isolated Supabase projects, and the Cloudflare account. The Cloudflare inventory currently includes `jarvis-control-worker`, `jarvis-gateio-attestor`, `jarvis-unified-mcp`, and the `jarvis-control-panel` Pages project. The control Worker already has a one-minute schedule; the Gate.io attestor and MCP Worker have no Cron schedules. These existing schedules and production Worker settings were inspected only and were not changed.

Render is not verified as connected; therefore Render workspace inspection, Cron creation, deployment and billing checks cannot be reported as completed. No JAEO Worker or JAEO Cron has been provisioned. A configured role is not a connected integration, and each write/deploy operation remains approval-gated.

## Rollout sequence

1. Apply the JAEO migration to the isolated prototype only.
2. Verify schema constraints, RLS and security advisors.
3. Run unit tests and PR CI.
4. Implement authenticated task/approval/feedback API and dashboard read model.
5. Connect provider adapters with least privilege and audit evidence.
6. Verify Render billing and service limits before any paid Cron provisioning.
7. Keep production and trading controls untouched throughout.

No production deployment, live trading, or 30-day paper-validation start is implied by this implementation.
