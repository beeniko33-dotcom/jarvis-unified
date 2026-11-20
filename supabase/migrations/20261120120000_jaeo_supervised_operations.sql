-- JAEO supervised operations registry. Apply first to the isolated prototype.
-- All records are private; browser roles receive no access.
create schema if not exists jarvis_private;
revoke all on schema jarvis_private from public, anon, authenticated;
grant usage on schema jarvis_private to service_role;

create table if not exists jarvis_private.jaeo_tasks (
    id uuid primary key default gen_random_uuid(),
    idempotency_key text not null unique check (char_length(idempotency_key) between 8 and 128),
    title text not null check (char_length(trim(title)) between 1 and 200),
    description text not null default '' check (char_length(description) <= 4000),
    agent_role text not null check (agent_role in (
        'orchestrator','engineering','database','infrastructure',
        'security','qa','research','release','audit'
    )),
    workspace_scope text not null default 'all' check (workspace_scope in ('all','core')),
    autonomy text not null default 'supervised' check (autonomy = 'supervised'),
    feedback_mode text not null default 'both' check (feedback_mode = 'both'),
    status text not null default 'queued' check (status in (
        'queued','running','awaiting_approval','completed','failed','blocked','cancelled'
    )),
    mode text not null default 'paper' check (mode = 'paper'),
    live_trading_enabled boolean not null default false check (live_trading_enabled = false),
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    result jsonb not null default '{}'::jsonb check (pg_column_size(result) <= 16384)
);
create index if not exists jaeo_tasks_status_created_idx
    on jarvis_private.jaeo_tasks (status, created_at desc);

create table if not exists jarvis_private.jaeo_approvals (
    id uuid primary key default gen_random_uuid(),
    task_id uuid not null references jarvis_private.jaeo_tasks(id) on delete restrict,
    action text not null check (action in (
        'change_code','change_schema','change_secret','provision_resource',
        'create_cron','deploy_preview','merge_pull_request'
    )),
    resource_id text not null check (char_length(trim(resource_id)) between 1 and 256),
    request jsonb not null default '{}'::jsonb check (pg_column_size(request) <= 8192),
    status text not null default 'pending' check (status in ('pending','approved','rejected','expired')),
    requested_at timestamptz not null default now(),
    decided_at timestamptz,
    decided_by text,
    decision_reason text check (decision_reason is null or char_length(decision_reason) <= 1000)
);
create index if not exists jaeo_approvals_pending_idx
    on jarvis_private.jaeo_approvals (requested_at)
    where status = 'pending';

create table if not exists jarvis_private.jaeo_feedback (
    id uuid primary key default gen_random_uuid(),
    task_id uuid not null references jarvis_private.jaeo_tasks(id) on delete restrict,
    agent_role text not null check (agent_role in (
        'orchestrator','engineering','database','infrastructure',
        'security','qa','research','release','audit'
    )),
    status text not null check (status in (
        'queued','running','awaiting_approval','completed','failed','blocked'
    )),
    payload jsonb not null check (pg_column_size(payload) <= 16384),
    occurred_at timestamptz not null default now()
);
create index if not exists jaeo_feedback_task_time_idx
    on jarvis_private.jaeo_feedback (task_id, occurred_at desc);

alter table jarvis_private.jaeo_tasks enable row level security;
alter table jarvis_private.jaeo_approvals enable row level security;
alter table jarvis_private.jaeo_feedback enable row level security;

revoke all on jarvis_private.jaeo_tasks, jarvis_private.jaeo_approvals,
    jarvis_private.jaeo_feedback from public, anon, authenticated;
grant select, insert, update on jarvis_private.jaeo_tasks to service_role;
grant select, insert, update on jarvis_private.jaeo_approvals to service_role;
grant select, insert on jarvis_private.jaeo_feedback to service_role;

create or replace function jarvis_private.jaeo_reject_feedback_mutation()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
    raise exception 'JAEO feedback is append-only';
end;
$$;
drop trigger if exists jaeo_feedback_append_only on jarvis_private.jaeo_feedback;
create trigger jaeo_feedback_append_only
before update or delete on jarvis_private.jaeo_feedback
for each row execute function jarvis_private.jaeo_reject_feedback_mutation();

comment on table jarvis_private.jaeo_tasks is
    'Private supervised JAEO task registry. Paper-only invariant is enforced by check constraints.';
comment on table jarvis_private.jaeo_approvals is
    'Human approval queue for bounded non-production operations. Production and live-trading actions are not approvable.';
comment on table jarvis_private.jaeo_feedback is
    'Append-only structured progress, test, error and evidence reports for dashboard and scheduled summaries.';
