-- Private audit trail for trusted platform verification decisions.
create table jarvis_private.platform_admin_audit (
  id uuid primary key default gen_random_uuid(),
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  action text not null check (action in ('career_org_verification','marketplace_seller_verification','career_member_invitation')),
  entity_type text not null check (entity_type in ('career_organization','marketplace_seller','career_organization_member')),
  entity_id uuid not null,
  from_status text,
  to_status text,
  reason text not null check (length(trim(reason)) between 5 and 1000),
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details) = 'object'),
  created_at timestamptz not null default now()
);
create index platform_admin_audit_entity_idx
  on jarvis_private.platform_admin_audit(entity_type, entity_id, created_at desc);
create index platform_admin_audit_actor_idx
  on jarvis_private.platform_admin_audit(actor_user_id, created_at desc);
alter table jarvis_private.platform_admin_audit enable row level security;
revoke all on jarvis_private.platform_admin_audit from public, anon, authenticated;
grant select, insert on jarvis_private.platform_admin_audit to service_role;
comment on table jarvis_private.platform_admin_audit is
  'Private append-only audit records for allowlisted platform administration actions. Not exposed through the browser Data API.';

-- Atomic verification decision. Only the server-side service role may execute this RPC;
-- the Edge Function validates the operator's bearer session before calling it.
create or replace function public.jarvis_platform_admin_verify_entity(
  p_actor_id uuid,
  p_entity_type text,
  p_entity_id uuid,
  p_status text,
  p_reason text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_from_status text;
  v_action text;
begin
  if p_actor_id is null or not exists (
    select 1 from public.operator_allowlist a where a.user_id = p_actor_id
  ) then
    raise exception 'operator_not_authorized' using errcode = '42501';
  end if;
  if p_status not in ('verified','rejected','suspended') then
    raise exception 'invalid_verification_status' using errcode = '22023';
  end if;
  if p_reason is null or length(trim(p_reason)) < 5 or length(p_reason) > 1000 then
    raise exception 'verification_reason_required' using errcode = '22023';
  end if;

  if p_entity_type = 'career_organization' then
    select verification_status into v_from_status
      from public.career_organizations where id = p_entity_id for update;
    if not found then raise exception 'organization_not_found' using errcode = 'P0002'; end if;
    update public.career_organizations set verification_status = p_status, updated_at = now()
      where id = p_entity_id;
    v_action := 'career_org_verification';
  elsif p_entity_type = 'marketplace_seller' then
    select verification_status into v_from_status
      from public.marketplace_sellers where id = p_entity_id for update;
    if not found then raise exception 'seller_not_found' using errcode = 'P0002'; end if;
    update public.marketplace_sellers set verification_status = p_status, updated_at = now()
      where id = p_entity_id;
    v_action := 'marketplace_seller_verification';
  else
    raise exception 'unsupported_entity_type' using errcode = '22023';
  end if;

  insert into jarvis_private.platform_admin_audit(
    actor_user_id, action, entity_type, entity_id, from_status, to_status, reason
  ) values (
    p_actor_id, v_action, p_entity_type, p_entity_id, v_from_status, p_status, trim(p_reason)
  );

  return jsonb_build_object(
    'entity_type', p_entity_type,
    'entity_id', p_entity_id,
    'from_status', v_from_status,
    'to_status', p_status,
    'audit_written', true
  );
end;
$$;
revoke all on function public.jarvis_platform_admin_verify_entity(uuid,text,uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.jarvis_platform_admin_verify_entity(uuid,text,uuid,text,text)
  to service_role;
comment on function public.jarvis_platform_admin_verify_entity(uuid,text,uuid,text,text) is
  'Atomic allowlist-checked employer/seller verification and audit. Service-role only; call through authenticated platform-admin Edge Function.';
