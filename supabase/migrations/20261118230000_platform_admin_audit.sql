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
