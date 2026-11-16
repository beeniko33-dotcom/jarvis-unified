-- The RLS auto-enable routine is an event-trigger callback, not an RPC.
-- Keep it callable by its owner/event-trigger machinery, not browser/API roles.
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable()
    FROM PUBLIC, anon, authenticated, service_role;
