-- JAEO operator administration audit trail (isolated QA first).
create table if not exists jarvis_private.jaeo_operator_admin_audit (
  id uuid primary key default gen_random_uuid(),
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  target_user_id uuid not null references auth.users(id) on delete restrict,
  action text not null check (action in ('grant_operator')),
  target_email text,
  detail jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now()
);

comment on table jarvis_private.jaeo_operator_admin_audit is
  'Append-only audit evidence for trusted JAEO operator grants. Role revocation remains a Supabase administrator operation.';

alter table jarvis_private.jaeo_operator_admin_audit enable row level security;
revoke all on jarvis_private.jaeo_operator_admin_audit from public, anon, authenticated;
grant usage on schema jarvis_private to service_role;
grant select, insert on jarvis_private.jaeo_operator_admin_audit to service_role;

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
  if current_setting('request.jwt.claim.role', true) is distinct from 'service_role' then
    raise exception 'service_role_required' using errcode = '42501';
  end if;
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

revoke all on function public.jaeo_record_operator_admin_event(uuid,uuid,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.jaeo_record_operator_admin_event(uuid,uuid,text,text,jsonb) to service_role;

create or replace function jarvis_private.prevent_operator_admin_audit_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'jaeo_operator_admin_audit_is_append_only' using errcode = '42501';
end;
$$;

drop trigger if exists jaeo_operator_admin_audit_immutable on jarvis_private.jaeo_operator_admin_audit;
create trigger jaeo_operator_admin_audit_immutable
before update or delete on jarvis_private.jaeo_operator_admin_audit
for each row execute function jarvis_private.prevent_operator_admin_audit_mutation();
