from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_jaeo_edge_function_auth_and_server_boundary():
    source = (ROOT / "supabase/functions/jaeo-operator/index.ts").read_text()
    assert "npm:@supabase/supabase-js@2.119.2" in source
    assert "auth.getUser(token)" in source
    assert "user.app_metadata?.jaeo_operator === true" in source
    assert "SUPABASE_SERVICE_ROLE_KEY" in source
    assert "SUPABASE_SECRET_KEYS" in source
    assert "SUPABASE_PUBLISHABLE_KEYS" in source
    assert 'admin.rpc("jaeo_operator_api"' in source
    assert 'admin.schema("jarvis_private")' not in source
    assert "JAEO_ALLOWED_ORIGINS" in source
    assert "jarvis-unified-portal.pages.dev" in source
    assert 'operation === "list_approvals"' in source
    assert "crypto.subtle.digest" in source


def test_jaeo_rpc_is_service_role_only_and_hardened():
    migration = (ROOT / "supabase/migrations/20261121110000_jaeo_operator_rpc.sql").read_text()
    assert "security definer" in migration.lower()
    assert "set search_path = ''" in migration.lower()
    assert "revoke all on function public.jaeo_operator_api" in migration.lower()
    assert "to service_role" in migration.lower()
    assert "jaeo_self_approval_denied" in migration
    assert "jaeo_production_resource_denied" in migration
    assert "Approval records authorization only" in migration
