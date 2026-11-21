# JAEO operator administration audit (isolated QA)

## Grant contract

The `grant_operator` Edge Function operation is owner-only. It requires a different, existing QA user with a confirmed email. It updates the target's trusted `app_metadata.jaeo_operator` claim, then records an append-only event through `public.jaeo_record_operator_admin_event`.

The audit RPC is executable only by the database `service_role` via explicit function ACLs. It deliberately does not inspect the legacy `request.jwt.claim.role` setting: Supabase secret API keys can be mapped to the service role without populating that legacy setting. The Edge Function must remain the only intended caller and must never expose its secret key to a browser.

If audit insertion fails after the Auth metadata update, the Edge Function attempts to restore the target's previous app metadata and returns an error. Because Auth Admin and Postgres are separate services, this is a compensating rollback, not a cross-service atomic transaction. The operation must be verified after failure.

## Historical QA discrepancy

The QA account for Brian currently has `app_metadata.jaeo_operator=true`, but the audit table contains no corresponding grant event. Supabase logs show a successful Auth Admin `PUT` followed by HTTP 403 from `jaeo_record_operator_admin_event` on 2026-11-21 13:13:39 UTC. The earlier audit function rejected the service-role call because its internal legacy JWT-claim check did not match the service-role request context.

The historical grant is therefore **not audit-verified**. Do not manufacture a backdated event or claim that the earlier operation was recorded. The new migration fixes future audit RPC authorization; a fresh, dedicated QA account should be used to test the complete grant-and-audit flow before this capability is treated as end-to-end verified.

## Scope

This is isolated QA only. It does not authorize production operator changes, JAEO action execution, deployments, trading, payments, or other external actions.
