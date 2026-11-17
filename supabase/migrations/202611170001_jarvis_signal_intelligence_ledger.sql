-- Jarvis signal intelligence ledger. Applied to Supabase project zythldptlplyutphgxpg.
create table if not exists jarvis_private.market_signals (
  signal_id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  instrument text not null,
  asset_class text not null check (asset_class in ('forex','crypto','index','commodity','other')),
  direction text not null check (direction in ('long','short','neutral')),
  timeframe text not null,
  strategy_id text not null,
  strategy_version text not null,
  created_at timestamptz not null,
  expires_at timestamptz,
  provider text not null,
  provider_observation_id uuid references jarvis_private.market_observations(id),
  market_data_trust text not null default 'unverified_market_data'
    check (market_data_trust in ('unverified_market_data','candidate_unverified','verified_provider')),
  evidence_credit boolean not null default false check (evidence_credit = false),
  quote jsonb not null default '{}'::jsonb,
  analysis jsonb not null default '{}'::jsonb,
  trade_plan jsonb not null default '{}'::jsonb,
  risk jsonb not null default '{}'::jsonb,
  status text not null default 'research_only'
    check (status in ('research_only','paper_eligible','expired','invalidated','rejected')),
  paper_execution jsonb not null default '{}'::jsonb,
  outcome jsonb not null default '{}'::jsonb,
  created_by text not null default 'jarvis-signal-engine',
  inserted_at timestamptz not null default now(),
  constraint market_signals_expiry_after_creation check (expires_at is null or expires_at > created_at)
);
create index if not exists market_signals_instrument_created_idx
  on jarvis_private.market_signals (instrument, created_at desc);
create index if not exists market_signals_status_created_idx
  on jarvis_private.market_signals (status, created_at desc);
create index if not exists market_signals_provider_created_idx
  on jarvis_private.market_signals (provider, created_at desc);
create index if not exists market_observations_symbol_event_idx
  on jarvis_private.market_observations (symbol, event_time desc);
create index if not exists market_observations_source_event_idx
  on jarvis_private.market_observations (source_id, event_time desc);
alter table jarvis_private.market_signals enable row level security;
revoke all on jarvis_private.market_signals from anon, authenticated;
grant select, insert, update on jarvis_private.market_signals to service_role;
comment on table jarvis_private.market_signals is
  'Auditable Jarvis signal records. Candidate/unverified market data cannot earn evidence credit or authorize live execution.';
comment on column jarvis_private.market_signals.evidence_credit is
  'Hard safety invariant: remains false until independent provider provenance verification and review.';
