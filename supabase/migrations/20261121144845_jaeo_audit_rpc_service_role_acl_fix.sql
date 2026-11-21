-- Fix JAEO operator-admin audit RPC authorization.
-- The function is already EXECUTE-restricted to service_role at the database ACL.
-- Do not depend on the legacy request.jwt.claim.role GUC: requests authenticated with
-- Supabase secret API keys can be mapped to service_role without populating that GUC.
create or replace function public.jaeo_record_operator_admin_event(
  p_actor_id uuid,
  p_target_id uuid,
  p_action text,
  p_target_email text,
  p_detail jsonb default '{}'::jsonb
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  if p_actor_id is null or p_target_id is null or p_actor_id = p_target_id
     or p_action <> 'grant_operator' or p_detail is null
     or jsonb_typeof(p_detail) <> 'object' then
    raise exception 'invalid_operator_admin_event' using errcode = '22023';
  end if;
  insert into jarvis_private.jaeo_operator_admin_audit
    (actor_user_id,target_user_id,action,target_email,detail)
  values (p_actor_id,p_target_id,p_action,left(p_target_email,320),p_detail)
  returning id into v_id;
  return v_id;
end;
$$;

revoke all on function public.jaeo_record_operator_admin_event(uuid,uuid,text,text,jsonb)
  from public, anon, authenticated;
grant execute on function public.jaeo_record_operator_admin_event(uuid,uuid,text,text,jsonb)
  to service_role;
