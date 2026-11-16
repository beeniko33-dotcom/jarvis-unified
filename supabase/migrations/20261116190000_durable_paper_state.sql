-- Durable, idempotent paper-cycle state. This schema never authorizes broker execution.
create table if not exists jarvis_private.paper_accounts (
    account_id text primary key check (length(trim(account_id)) between 1 and 128),
    mode text not null default 'paper' check (mode = 'paper'),
    revision bigint not null check (revision > 0),
    state jsonb not null,
    state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
    last_run_id uuid not null,
    updated_at timestamptz not null default now()
);

create table if not exists jarvis_private.paper_runs (
    run_id uuid primary key,
    account_id text not null references jarvis_private.paper_accounts(account_id),
    mode text not null default 'paper' check (mode = 'paper'),
    status text not null check (status in ('completed')),
    revision_before bigint not null check (revision_before >= 0),
    revision_after bigint not null check (revision_after = revision_before + 1),
    input_sha256 text not null check (input_sha256 ~ '^[0-9a-f]{64}$'),
    state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
    started_at timestamptz not null,
    completed_at timestamptz not null,
    metadata jsonb not null default '{}'::jsonb
);

create index if not exists paper_runs_account_completed_idx
    on jarvis_private.paper_runs (account_id, completed_at desc);

create table if not exists jarvis_private.paper_ledger_events (
    id uuid primary key default gen_random_uuid(),
    account_id text not null references jarvis_private.paper_accounts(account_id),
    run_id uuid not null references jarvis_private.paper_runs(run_id),
    sequence bigint not null check (sequence > 0),
    event_type text not null check (length(trim(event_type)) between 1 and 128),
    occurred_at timestamptz not null,
    payload jsonb not null,
    previous_hash text not null,
    event_hash text not null check (event_hash ~ '^[0-9a-f]{64}$'),
    unique (account_id, sequence),
    unique (account_id, event_hash)
);

create index if not exists paper_ledger_events_run_idx
    on jarvis_private.paper_ledger_events (run_id, sequence);

alter table jarvis_private.paper_accounts enable row level security;
alter table jarvis_private.paper_runs enable row level security;
alter table jarvis_private.paper_ledger_events enable row level security;

revoke all on jarvis_private.paper_accounts, jarvis_private.paper_runs,
    jarvis_private.paper_ledger_events from public, anon, authenticated;
grant select, insert, update on jarvis_private.paper_accounts to service_role;
grant select, insert on jarvis_private.paper_runs to service_role;
grant select, insert on jarvis_private.paper_ledger_events to service_role;

create or replace function jarvis_private.reject_paper_ledger_mutation()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
    raise exception 'paper ledger events are append-only';
end;
$$;

drop trigger if exists paper_ledger_events_append_only on jarvis_private.paper_ledger_events;
create trigger paper_ledger_events_append_only
before update or delete on jarvis_private.paper_ledger_events
for each row execute function jarvis_private.reject_paper_ledger_mutation();

revoke all on function jarvis_private.reject_paper_ledger_mutation()
    from public, anon, authenticated, service_role;

comment on table jarvis_private.paper_accounts is
    'Latest durable paper-only account snapshot. State hash and revision are checked on every load/commit.';
comment on table jarvis_private.paper_runs is
    'Idempotency ledger for atomically committed paper cycles. Contains no live broker authorization.';
comment on table jarvis_private.paper_ledger_events is
    'Append-only, per-account SHA-256 chained paper-cycle events.';
