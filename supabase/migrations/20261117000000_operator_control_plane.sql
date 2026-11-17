-- Operator control plane: remote monitoring and paper-only controls.
-- Browsers never touch these tables. Edge Functions (service role) verify the operator and
-- enqueue commands; the local control worker (service role) claims and executes them.
-- LIVE TRADING IS NOT AN ACTION. The check constraint below makes that a database fact.

create table if not exists public.operator_allowlist (
    user_id uuid primary key references auth.users (id) on delete cascade,
    added_at timestamptz not null default now(),
    note text check (note is null or char_length(note) <= 200)
);

create table if not exists public.operator_commands (
    id uuid primary key default gen_random_uuid(),
    action text not null check (action in (
        'pause_entries',
        'resume_entries',
        'engage_kill_switch',
        'run_paper_session'
    )),
    requested_by uuid not null references auth.users (id) on delete restrict,
    requested_at timestamptz not null default now(),
    idempotency_key text not null unique check (char_length(idempotency_key) between 8 and 128),
    reason text check (reason is null or char_length(reason) <= 300),
    status text not null default 'pending' check (status in (
        'pending', 'claimed', 'completed', 'rejected', 'failed'
    )),
    claimed_by text,
    claimed_at timestamptz,
    completed_at timestamptz,
    result jsonb not null default '{}'::jsonb check (pg_column_size(result) <= 8192),
    constraint claimed_has_worker check (status not in ('claimed', 'completed', 'rejected', 'failed') or claimed_by is not null)
);

create index if not exists operator_commands_pending_idx
    on public.operator_commands (requested_at)
    where status = 'pending';
create index if not exists operator_commands_requested_idx
    on public.operator_commands (requested_at desc);

create table if not exists public.operator_status (
    worker_id text primary key check (char_length(worker_id) between 1 and 128),
    reported_at timestamptz not null,
    health text not null check (health in ('healthy', 'degraded', 'stopped', 'blocked')),
    mode text not null default 'paper' check (mode = 'paper'),
    kill_switch_engaged boolean not null,
    entries_paused boolean not null,
    last_paper_session_date text check (last_paper_session_date is null or last_paper_session_date ~ '^\d{4}-\d{2}-\d{2}$'),
    details jsonb not null default '{}'::jsonb check (pg_column_size(details) <= 8192),
    updated_at timestamptz not null default now()
);

-- Lock down: no browser or public access at all. Only the service role (Edge Functions and the
-- trusted local worker) can read or write these tables.
alter table public.operator_allowlist enable row level security;
alter table public.operator_commands enable row level security;
alter table public.operator_status enable row level security;

revoke all on public.operator_allowlist, public.operator_commands, public.operator_status
    from public, anon, authenticated;
grant select, insert, update, delete on public.operator_allowlist,
    public.operator_commands, public.operator_status to service_role;

comment on table public.operator_allowlist is
    'Users allowed to use the control panel. Populated manually by the project owner; never by the browser.';
comment on table public.operator_commands is
    'Paper-only operator command queue. The action set is fixed by check constraint and contains no live-trading action.';
comment on table public.operator_status is
    'Latest health snapshot reported by the local control worker. Paper mode only.';
