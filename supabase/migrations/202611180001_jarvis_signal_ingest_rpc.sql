-- Idempotent write path for paper-trading signals into the private signal ledger.
-- Remote callers can only create research_only rows with no evidence credit; promotion to any
-- other status remains a separate, reviewed step. This function never authorizes execution.
create or replace function public.jarvis_ingest_market_signal(p_signal jsonb)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  new_id uuid;
  key_value text := p_signal->>'idempotency_key';
  created_ts timestamptz;
begin
  if jsonb_typeof(p_signal) <> 'object' then raise exception 'signal must be an object'; end if;
  if coalesce(length(key_value), 0) not between 8 and 160
     or coalesce(length(trim(p_signal->>'instrument')), 0) not between 3 and 24
     or coalesce(length(trim(p_signal->>'timeframe')), 0) not between 1 and 8
     or coalesce(length(trim(p_signal->>'strategy_id')), 0) not between 1 and 64
     or coalesce(length(trim(p_signal->>'strategy_version')), 0) not between 1 and 32
     or coalesce(length(trim(p_signal->>'provider')), 0) not between 1 and 32
     or (p_signal->>'asset_class') not in ('forex','crypto','index','commodity','other')
     or (p_signal->>'direction') not in ('long','short','neutral')
     or coalesce(jsonb_typeof(p_signal->'quote'), '') <> 'object'
     or coalesce(jsonb_typeof(p_signal->'analysis'), '') <> 'object'
     or coalesce(jsonb_typeof(p_signal->'risk'), '') <> 'object'
     or coalesce(jsonb_typeof(p_signal->'paper_execution'), '') <> 'object'
  then raise exception 'signal schema validation failed'; end if;
  created_ts := (p_signal->>'created_at')::timestamptz;

  insert into jarvis_private.market_signals(
    idempotency_key, instrument, asset_class, direction, timeframe, strategy_id, strategy_version,
    created_at, provider, market_data_trust, evidence_credit, quote, analysis, risk, paper_execution,
    status, created_by)
  values(
    key_value, upper(trim(p_signal->>'instrument')), p_signal->>'asset_class', p_signal->>'direction',
    trim(p_signal->>'timeframe'), trim(p_signal->>'strategy_id'), trim(p_signal->>'strategy_version'),
    created_ts, trim(p_signal->>'provider'), 'unverified_market_data', false,
    p_signal->'quote', p_signal->'analysis', p_signal->'risk', p_signal->'paper_execution',
    'research_only', 'jarvis-live-signal-runner')
  on conflict (idempotency_key) do nothing
  returning signal_id into new_id;

  return jsonb_build_object('inserted', new_id is not null, 'signal_id', new_id,
    'status', 'research_only', 'evidence_credit', false);
end; $$;
revoke all on function public.jarvis_ingest_market_signal(jsonb) from public, anon, authenticated;
grant execute on function public.jarvis_ingest_market_signal(jsonb) to service_role;
