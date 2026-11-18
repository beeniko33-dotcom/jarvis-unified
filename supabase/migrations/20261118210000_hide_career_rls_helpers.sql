-- Keep SECURITY DEFINER RLS helpers outside the PostgREST-exposed public schema.
-- These helpers remain callable by RLS expressions, but are not public RPC endpoints.

create schema if not exists jarvis_private;
revoke all on schema jarvis_private from public, anon, authenticated, service_role;
grant usage on schema jarvis_private to authenticated, service_role;

alter function public.career_is_org_member(uuid, text[])
  set schema jarvis_private;
alter function public.career_can_access_application(uuid)
  set schema jarvis_private;

create or replace function jarvis_private.career_can_access_application(p_application uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from public.career_applications a
    join public.career_jobs j on j.id = a.job_id
    where a.id = p_application
      and (
        a.candidate_id = auth.uid()
        or jarvis_private.career_is_org_member(j.organization_id, null)
      )
  );
$function$;

revoke all on function jarvis_private.career_is_org_member(uuid, text[]) from public, anon, authenticated, service_role;
revoke all on function jarvis_private.career_can_access_application(uuid) from public, anon, authenticated, service_role;
grant execute on function jarvis_private.career_is_org_member(uuid, text[]) to authenticated, service_role;
grant execute on function jarvis_private.career_can_access_application(uuid) to authenticated, service_role;

comment on schema jarvis_private is
  'Non-API schema for privileged internal helpers; do not add to PostgREST exposed schemas.';
