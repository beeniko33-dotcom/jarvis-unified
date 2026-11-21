from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_jaeo_edge_function_auth_and_server_boundary():
    source = (ROOT / "supabase/functions/jaeo-operator/index.ts").read_text()
    assert "npm:@supabase/supabase-js@2.119.2" in source
    assert "auth.getUser(token)" in source
    assert "user.app_metadata?.jaeo_operator === true" in source
    assert "JAEO_BOOTSTRAP_OWNER_USER_ID" in source
    assert "isOwner(user)" in source
    assert "SUPABASE_SERVICE_ROLE_KEY" in source
    assert "SUPABASE_SECRET_KEYS" in source
    assert "SUPABASE_PUBLISHABLE_KEYS" in source
    assert 'admin.rpc("jaeo_operator_api"' in source
    assert 'admin.schema("jarvis_private")' not in source
    assert 'req.method === "OPTIONS"' in source
    assert 'new Response(null, { status: 204' in source
    assert "Handle browser preflight before reading environment variables" in source
    assert "jarvis-unified-portal.pages.dev" in source
    assert 'operation === "list_approvals"' in source
    assert "crypto.subtle.digest" in source
    assert "containsSensitiveMaterial" in source
    assert "change_secret" not in source
    assert "rollbackConfirmed" in source
    assert "operator-role rollback could not be confirmed" in source


def test_jaeo_rpc_is_service_role_only_and_hardened():
    migration = (ROOT / "supabase/migrations/20261121110000_jaeo_operator_rpc.sql").read_text()
    assert "security definer" in migration.lower()
    assert "set search_path = ''" in migration.lower()
    assert "revoke all on function public.jaeo_operator_api" in migration.lower()
    assert "to service_role" in migration.lower()
    assert "jaeo_self_approval_denied" in migration
    assert "jaeo_production_resource_denied" in migration
    assert "Approval records authorization only" in migration


def test_jaeo_operator_admin_audit_rpc_uses_database_acl_not_legacy_claim_guc():
    migration = (ROOT / "supabase/migrations/20261121144845_jaeo_audit_rpc_service_role_acl_fix.sql").read_text()
    assert "security definer" in migration.lower()
    assert "set search_path = ''" in migration.lower()
    assert "revoke all on function public.jaeo_record_operator_admin_event" in migration.lower()
    assert "from public, anon, authenticated" in migration.lower()
    assert "grant execute on function public.jaeo_record_operator_admin_event" in migration.lower()
    assert "to service_role" in migration.lower()
    assert "current_setting('request.jwt.claim.role'" not in migration
    assert "jaeo_operator_admin_audit" in migration
