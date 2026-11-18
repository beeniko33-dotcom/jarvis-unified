-- Supervised Autopilot task intake. Tasks are proposals only; no executor is granted by this schema.
create table if not exists public.jarvis_autopilot_tasks (
  id uuid primary key default gen_random_uuid(),
  requested_by uuid not null references auth.users(id) on delete restrict,
  requested_at timestamptz not null default now(),
  task_text text not null check (char_length(task_text) between 12 and 4000),
  status text not null default 'awaiting_approval'
    check (status in ('awaiting_approval','approved','rejected','completed','failed','cancelled')),
  executor_state text not null default 'disabled'
    check (executor_state = 'disabled'),
  approval_required boolean not null default true,
  approved_by uuid references auth.users(id) on delete restrict,
  approved_at timestamptz,
  result jsonb not null default '{}'::jsonb check (pg_column_size(result) <= 8192),
  constraint approval_metadata_consistent check (
    (status <> 'approved' or (approved_by is not null and approved_at is not null))
  )
);
create index if not exists jarvis_autopilot_tasks_requested_idx
  on public.jarvis_autopilot_tasks(requested_at desc);
alter table public.jarvis_autopilot_tasks enable row level security;
revoke all on public.jarvis_autopilot_tasks from public, anon, authenticated;
grant select, insert, update, delete on public.jarvis_autopilot_tasks to service_role;
comment on table public.jarvis_autopilot_tasks is
  'Supervised AI task proposals. Executor is hard-disabled; proposals require human review and no task runs automatically.';
