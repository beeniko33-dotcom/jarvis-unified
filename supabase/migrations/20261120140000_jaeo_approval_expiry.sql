-- Bind JAEO approvals to a short validity window.
-- The application must still verify the row against the task/action/resource.
alter table jarvis_private.jaeo_approvals
    add column if not exists expires_at timestamptz
    not null default (now() + interval '15 minutes');

create index if not exists jaeo_approvals_task_status_expiry_idx
    on jarvis_private.jaeo_approvals (task_id, status, expires_at);

comment on column jarvis_private.jaeo_approvals.expires_at is
    'Approval validity deadline; expired approvals cannot authorize execution.';
