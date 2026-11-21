# Jarvis Unified release-readiness evidence — 2026-11-21

## Purpose and decision

This document records the verified state of the four-pillar project after the JAEO approval-expiry and audit-RPC fixes. It is an evidence register, not a declaration that the product is complete.

**Release decision: NOT READY for a general public product launch.** The isolated QA foundation is healthy and the latest main-branch CI is green, but Marketplace and Career are not deployed as working customer applications, Forex provenance is blocked, and JAEO is currently an approval/audit console without an action executor.

## Verified repository and deployment baseline

- Repository: `beeniko33-dotcom/jarvis-unified`
- Main commit inspected: `07712a0c1d1c9d388272d27ff1c1ceef744a07df`
- Latest CI run: [44921535535](https://github.com/beeniko33-dotcom/jarvis-unified/actions/runs/44921535535), completed successfully; its `test` job passed.
- Latest verified CI job includes dependency installation, public portal boundary checks, Forex forecast tests, repository regression tests, JAEO policy tests, Deriv read-only collector tests, foundation diagnostics and container smoke test.
- Cloudflare Pages production deployments from this main commit were previously confirmed successful:
  - [Jarvis Unified Portal](https://jarvis-unified-portal.pages.dev)
  - [Jarvis Control Panel](https://jarvis-control-panel.pages.dev)
- The portal is an informational landing page plus the isolated JAEO QA console. The legacy control-panel project is not evidence that the four-pillar target application is complete.

## Isolated Supabase QA evidence

Project: `jarvis-unified-isolated-qa` (`guvszwxvmitdvykvtsnc`), region `eu-west-1`, status `ACTIVE_HEALTHY`.

The QA project is separate from the paused production and legacy prototype projects. It has the selected QA migrations recorded below; it has **not** received the full repository migration chain.

Recorded QA migration versions:
- `20261121064146` career_giver_secure_foundation
- `20261121064148` hide_career_rls_helpers
- `20261121064150` marketplace_affiliate_foundation
- `20261121064151` marketplace_secure_order_rpc
- `20261121064153` jaeo_supervised_operations
- `20261121064154` jaeo_approval_expiry
- `20261121064219` optimize_public_rls_auth_uid_initplans
- `20261121064220` jarvis_qa_rls_and_fk_hardening
- `20261121064235` jarvis_qa_rls_fk_hardening
- `20261121064453` jaeo_supervised_research_mode
- `20261121064711` jaeo_task_request_binding
- `20261121064754` jaeo_requester_indexes
- `20261121070219` jaeo_operator_rpc
- `20261121071008` jaeo_approval_queue
- `20261121071641` jaeo_reject_secret_actions
- `20261121084200` jaeo_operator_admin_audit
- `20261121084214` jaeo_operator_admin_audit_indexes
- `20261121144845` jaeo_audit_rpc_service_role_acl_fix

### QA function inventory

Only `jaeo-operator` is deployed in this QA project. It is ACTIVE at version 13 with `verify_jwt=true`. Marketplace order, Career and Forex collector Edge Functions are not present in this QA project's current function inventory.

### Row-level security snapshot

All 11 inspected public application tables have RLS enabled and at least one policy:
- Career: `career_applications`, `career_conversations`, `career_jobs`, `career_messages`, `career_organization_members`, `career_organizations`, `career_profiles`.
- Marketplace: `marketplace_affiliate_links`, `marketplace_listings`, `marketplace_orders`, `marketplace_sellers`.

The four `jarvis_private` JAEO tables have RLS enabled and no direct policies. This is intentional for the private schema and must remain inaccessible to browser roles; access is through restricted server-side functions/RPCs.

### Advisors

- Health Advisor: no findings.
- Security Advisor: four informational `rls_enabled_no_policy` findings on private JAEO tables (intentional private-schema design) and one warning for leaked-password protection being unavailable on the current Free plan.
- Performance Advisor: 19 unused-index informational findings. Do not drop indexes based solely on a fresh, low-traffic QA database; reassess after representative workload evidence.

## Four-pillar release gates

### 1. Forex Signal Intelligence — BLOCKED

Existing deterministic forecast engine and tests support bullish/bearish/neutral research forecasts from fresh chronological OHLC candles. This is not proof of a verified FX market-data service.

The market-data candidate assessment remains `BLOCKED_PROVENANCE`, with zero verified forward days and no started 30-day validation period. Candidate Biquote/Deriv feeds must remain explicitly unverified and cannot receive evidence credit. No Forex-facing route may expose paper/demo/live execution, order placement, position management or broker execution.

Required before release:
1. Independently establish source identity, instrument semantics, permitted use and provenance evidence.
2. Keep candidate feeds visibly unverified until the provider-specific trust contract is satisfied.
3. Persist immutable observation and forecast lineage, freshness and invalidation states.
4. Add user-facing watchlists, history and opt-in alerts only after data quality and privacy tests.
5. Remove/retire legacy execution paths from Forex routing through dependency-aware changes and regression coverage.

### 2. Marketplace — BLOCKED

Marketplace schema and browser UI foundations exist. The UI correctly describes order records as intents and keeps payments, fulfilment, commissions and rewards inactive.

The QA project has Marketplace tables/RLS but does not currently have the Marketplace order Edge Function deployed. The existing UI lives under `apps/control_panel`; a working end-to-end deployment against the isolated QA project, including environment config, CORS, auth, seller verification, listing lifecycle and order-intent idempotency, has not been verified.

Required before release:
1. Establish a dedicated app deployment/configuration for the isolated QA environment.
2. Deploy and test the Marketplace function only after reviewing its current code and required environment variables.
3. Verify seller ownership, trusted verification, listing visibility, buyer access and order ownership with negative cross-user tests.
4. Keep all money movement, payments, fulfilment, affiliate commission and rewards disabled until separately designed and approved.

### 3. Career — BLOCKED

Career schema and UI foundations exist, including candidate profiles, organizations, jobs, applications and private messaging. The UI explicitly keeps employer publishing pending trusted verification.

The QA project has Career tables/RLS, but no end-to-end browser verification was recorded. The full repository migration chain contains overlapping Career foundation migrations; do not apply the full chain in timestamp order until it has been reconciled and tested against a fresh disposable database.

Required before release:
1. Resolve overlapping migration history with a forward-only canonical schema and test the complete chain on a fresh disposable database.
2. Verify candidate/employer ownership and conversation participant isolation, including cross-account negative tests.
3. Add safe employer verification and job publishing review.
4. Verify CV privacy, file access and deletion/retention behavior.
5. Keep external application submission behind explicit user review and approval.

### 4. JAEO — PARTIAL / QA ONLY

JAEO supports authenticated task intake, task-bound approvals, expiry/reason validation, operator administration and audit records in the isolated QA project. Approval records do not execute actions.

The current QA inventory contains only `jaeo-operator` v13 with JWT verification enabled. There is no approved execution worker or production action runtime. This is intentional for the current stage.

Required before any broader rollout:
1. Complete browser-level sign-in, task intake, request binding, approval/denial, expiry and audit-history tests.
2. Verify non-owner/operator role restrictions and cross-user task isolation.
3. Add alerting/monitoring and human support handoff.
4. Preserve distinct human approval, deny-by-default, no self-approval, no self-elevation and append-only audit evidence.
5. Do not add a worker or enable external actions until each action type has a threat model, least-privilege adapter, idempotency, rollback strategy and explicit approval design.

## Open pull requests requiring separate disposition

- [PR #189 — adaptive workspace and Gate.io/Bybit market universe](https://github.com/beeniko33-dotcom/jarvis-unified/pull/189): 7 commits ahead and 258 behind current main at the time of inspection. It modifies the legacy control-panel trading workspace. Do not merge as-is; extract only independently reviewed, still-relevant UI changes into a fresh branch.
- [PR #158 — market signal observation FK index](https://github.com/beeniko33-dotcom/jarvis-unified/pull/158): 4 commits ahead and 298 behind current main. It also changes a legacy runtime-ingest workflow. Review the migration against the current schema and recreate a minimal current-branch PR if the index is still needed. Do not merge as-is.

## Budget and security constraints

- Keep the architecture free-first; no paid domain, plan upgrade, or paid provisioning is authorized.
- Production Supabase and the legacy prototype remain paused and untouched.
- Do not expose Supabase secret/service-role credentials in browser code.
- Leaked-password protection remains unavailable on the Free plan; do not upgrade solely to clear that warning.
- No live/demo/paper trading runtime, payment processing, reward issuance, or unsupervised JAEO execution is part of this release.

## Release acceptance checklist

A public launch may be reconsidered only when all applicable items have verifiable evidence:

- [ ] Fresh-database migration chain reconciles and applies cleanly.
- [ ] All exposed tables have intentional RLS policies and cross-tenant negative tests.
- [ ] Marketplace and Career are deployed to isolated QA and pass end-to-end tests.
- [ ] Forex data provenance gate is satisfied or the product is explicitly launched as unverified research with no misleading claims.
- [ ] JAEO role, approval, expiry, payload-binding and audit tests pass in browser and server environments.
- [ ] Legacy trading UI/runtime is not reachable from the Forex product and stale deployment artifacts are contained.
- [ ] CI passes on the exact release commit; required `test` status check remains enabled on `main`.
- [ ] Cloudflare Pages deployment and browser/device smoke tests pass.
- [ ] Security, privacy, incident response, backup/restore and rollback reviews are documented.
- [ ] Human release owner explicitly approves the release.

**Current state:** CI and isolated QA foundations are healthy; the four-pillar customer product is not yet release-complete.
