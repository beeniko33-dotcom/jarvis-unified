-- Jarvis Unified Supabase control-plane foundation.
-- Runtime access is service-role only. Never expose this schema directly to browsers.
create schema if not exists jarvis_private;
revoke all on schema jarvis_private from public, anon, authenticated;
grant usage on schema jarvis_private to service_role;

create table if not exists jarvis_private.market_observations (
    id uuid primary key default gen_random_uuid(),
    source_id text not null check (length(trim(source_id)) between 1 and 128),
    event_time timestamptz not null,
    received_at timestamptz not null,
    symbol text not null check (length(trim(symbol)) between 1 and 64),
    timeframe text not null check (length(trim(timeframe)) between 1 and 32),
    schema_version integer not null check (schema_version > 0),
    content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
    values_json jsonb not null,
    out_of_order boolean not null default false,
    stale boolean not null default false,
    clock_skew boolean not null default false,
    provenance text not null default 'candidate_unverified'
        check (provenance = 'candidate_unverified'),
    inserted_at timestamptz not null default now(),
    unique (source_id, content_hash)
);

create index if not exists market_observations_source_time_idx
    on jarvis_private.market_observations (source_id, symbol, timeframe, event_time desc);
create index if not exists market_observations_inserted_idx
    on jarvis_private.market_observations (inserted_at desc);

create table if not exists jarvis_private.runtime_audit_events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null check (length(trim(event_type)) between 1 and 128),
    occurred_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    correlation_id text,
    component text not null check (length(trim(component)) between 1 and 128),
    payload jsonb not null default '{}'::jsonb,
    payload_sha256 text check (payload_sha256 is null or payload_sha256 ~ '^[0-9a-f]{64}$')
);

create index if not exists runtime_audit_events_occurred_idx
    on jarvis_private.runtime_audit_events (occurred_at desc);
create index if not exists runtime_audit_events_correlation_idx
    on jarvis_private.runtime_audit_events (correlation_id)
    where correlation_id is not null;

create table if not exists jarvis_private.worker_heartbeats (
    worker_id text primary key check (length(trim(worker_id)) between 1 and 128),
    worker_type text not null check (length(trim(worker_type)) between 1 and 64),
    reported_at timestamptz not null,
    started_at timestamptz,
    software_version text not null,
    git_commit text,
    mode text not null default 'paper' check (mode = 'paper'),
    health text not null check (health in ('healthy', 'degraded', 'stopped', 'blocked')),
    details jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

-- Defense in depth: the browser roles receive no privileges, even if RLS is
-- accidentally disabled later. The service role is the trusted backend only.
alter table jarvis_private.market_observations enable row level security;
alter table jarvis_private.runtime_audit_events enable row level security;
alter table jarvis_private.worker_heartbeats enable row level security;

revoke all on all tables in schema jarvis_private from public, anon, authenticated;
grant select, insert on jarvis_private.market_observations to service_role;
grant select, insert on jarvis_private.runtime_audit_events to service_role;
grant select, insert, update on jarvis_private.worker_heartbeats to service_role;

create or replace function jarvis_private.reject_append_only_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    raise exception 'append-only evidence records cannot be updated or deleted';
end;
$$;

drop trigger if exists market_observations_append_only on jarvis_private.market_observations;
create trigger market_observations_append_only
before update or delete on jarvis_private.market_observations
for each row execute function jarvis_private.reject_append_only_mutation();

drop trigger if exists runtime_audit_events_append_only on jarvis_private.runtime_audit_events;
create trigger runtime_audit_events_append_only
before update or delete on jarvis_private.runtime_audit_events
for each row execute function jarvis_private.reject_append_only_mutation();

comment on schema jarvis_private is
    'Private Jarvis runtime data. Access only from trusted server-side workers using Supabase service role.';
comment on table jarvis_private.market_observations is
    'Append-only market observations. Provenance is always candidate_unverified until an independent verifier is implemented.';
comment on table jarvis_private.runtime_audit_events is
    'Append-only operational audit events. Payloads must be allowlisted and scrubbed of credentials before insertion.';
comment on table jarvis_private.worker_heartbeats is
    'Latest worker health snapshot. mode is constrained to paper.';
