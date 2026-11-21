# Jarvis Autonomous Engineering & Operations (JAEO)

## Configured operating mode

- Autonomy: **supervised**
- Task mode: **research and engineering operations only**
- Workspace scope: **all** (discoverable connected workspaces; not a claim that every provider is connected)
- Feedback: **both** dashboard and reports
- Trading: **no paper, demo, or live trading; no order execution**
- Production operator controls: immutable to JAEO
- Budget: plan for no more than **₦5,000/month**; paid provisioning is blocked until current account billing and total exposure are verified.

## Agent roles

Orchestrator, Engineering, Database, Infrastructure, Security, QA, Research, Release and Audit are policy roles. A role name does not itself create an external model, worker, credential or provider connection. Each provider must be separately connected and verified.

## Permission model

Low-risk inspection, research, tests, branch creation and pull-request preparation can proceed. Code changes, schema changes, secret changes, provisioning, Cron creation, preview deployments and merges require explicit human approval recorded against the exact task, action, resource and canonical payload hash. The requester cannot approve their own request; the approver must be a different authenticated human. Production deployments, production operator-control changes and all trading actions are denied even if an approval is supplied.

Forex Signal Intelligence is read-only research. JAEO may organize observations, tests and engineering work, but it cannot create trade signals with execution instructions, orders, positions, sizing, entries, exits or broker requests. Never place credentials in task payloads or feedback.

Production resource identifiers are denylisted, including the production Supabase project and production control Worker.

## Task and feedback lifecycle

Tasks use a durable UUID, unique idempotency key, authenticated requester, explicit agent role, workspace scope, fixed supervised autonomy and dashboard-plus-report feedback. Approval rows are bound to the task requester and immutable action/resource/request hash; database triggers reject self-approval and edits after a decision. Feedback records capture status, inspected/changed resources, tests, deployment state, errors, evidence URLs and recommendations. Feedback is append-only. Learning reports are proposals for human review; they cannot change policy or self-modify.

## Integration truth

Read-only access is verified for the GitHub repository, the isolated Supabase QA project, and the Cloudflare account. Production Supabase projects remain paused and untouched. Legacy trading Workers and execution paths are not part of the four-pillar research-only release.

Render is not verified as connected; therefore Render workspace inspection, Cron creation, deployment and billing checks cannot be reported as completed. No JAEO Worker or JAEO Cron has been provisioned. A configured role is not a connected integration, and each write/deploy operation remains approval-gated.

## Rollout sequence

1. Apply the JAEO migration to the isolated QA project only.
2. Verify schema constraints, RLS and security advisors.
3. Run unit tests and PR CI.
4. Implement authenticated task/approval/feedback API and dashboard read model.
5. Connect provider adapters with least privilege and audit evidence.
6. Verify billing and service limits before any paid resource provisioning.
7. Keep production and trading controls untouched throughout.

No production deployment, paper validation, live trading, or 30-day paper-validation start is implied by this implementation.
