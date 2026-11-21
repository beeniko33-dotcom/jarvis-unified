-- Bind each JAEO task and approval to an authenticated requester.
-- Approval decisions must be made by a different authenticated human and
-- bound to the SHA-256 hash of the exact canonical action payload.
alter table jarvis_private.jaeo_tasks
  add column if not exists requested_by uuid references auth.users(id) on delete restrict;

alter table jarvis_private.jaeo_approvals
  add column if not exists requested_by uuid references auth.users(id) on delete restrict,
  add column if not exists decided_by_user_id uuid references auth.users(id) on delete restrict,
  add column if not exists request_hash text;

create or replace function jarvis_private.jaeo_require_task_requester()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if new.requested_by is null then
    raise exception 'jaeo_task_requester_required' using errcode = '23502';
  end if;
  return new;
end;
$function$;
revoke all on function jarvis_private.jaeo_require_task_requester() from public, anon, authenticated, service_role;
drop trigger if exists jaeo_task_requester_required on jarvis_private.jaeo_tasks;
create trigger jaeo_task_requester_required
before insert or update of requested_by on jarvis_private.jaeo_tasks
for each row execute function jarvis_private.jaeo_require_task_requester();

create or replace function jarvis_private.jaeo_validate_approval_binding()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_requester uuid;
begin
  select t.requested_by into v_requester
  from jarvis_private.jaeo_tasks t
  where t.id = new.task_id;

  if v_requester is null then
    raise exception 'jaeo_task_requester_missing' using errcode = '23514';
  end if;
  if new.requested_by is distinct from v_requester then
    raise exception 'jaeo_approval_requester_mismatch' using errcode = '23514';
  end if;
  if new.request_hash is null or new.request_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'jaeo_approval_request_hash_invalid' using errcode = '23514';
  end if;

  if tg_op = 'UPDATE' then
    if old.status <> 'pending' then
      raise exception 'jaeo_approval_decision_immutable' using errcode = '23514';
    end if;
    if new.task_id is distinct from old.task_id
       or new.action is distinct from old.action
       or new.resource_id is distinct from old.resource_id
       or new.requested_by is distinct from old.requested_by
       or new.request_hash is distinct from old.request_hash then
      raise exception 'jaeo_approval_binding_immutable' using errcode = '23514';
    end if;
  end if;

  if new.status in ('approved','rejected') then
    if new.decided_by_user_id is null
       or new.decided_at is null
       or new.decided_by_user_id = v_requester then
      raise exception 'jaeo_distinct_human_approver_required' using errcode = '42501';
    end if;
  elsif new.status = 'pending' then
    if new.decided_by_user_id is not null or new.decided_at is not null then
      raise exception 'jaeo_pending_approval_cannot_have_decision' using errcode = '23514';
    end if;
  end if;

  return new;
end;
$function$;
revoke all on function jarvis_private.jaeo_validate_approval_binding() from public, anon, authenticated, service_role;
drop trigger if exists jaeo_approval_request_binding on jarvis_private.jaeo_approvals;
create trigger jaeo_approval_request_binding
before insert or update on jarvis_private.jaeo_approvals
for each row execute function jarvis_private.jaeo_validate_approval_binding();

comment on column jarvis_private.jaeo_tasks.requested_by is
  'Authenticated human requester. New tasks require this field; legacy rows may remain null until reviewed.';
comment on column jarvis_private.jaeo_approvals.requested_by is
  'Must match the parent task requester; immutable after approval request creation.';
comment on column jarvis_private.jaeo_approvals.decided_by_user_id is
  'Authenticated human decision-maker. Must differ from requested_by for approve/reject decisions.';
comment on column jarvis_private.jaeo_approvals.request_hash is
  'Lowercase SHA-256 hash of the exact canonical action payload; immutable after request creation.';
