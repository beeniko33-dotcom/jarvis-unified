-- Support joins and parent-row updates/deletes for provider-linked market signals.
-- Applied to the connected Supabase project; IF NOT EXISTS keeps replay safe.
create index if not exists market_signals_provider_observation_id_idx
  on jarvis_private.market_signals (provider_observation_id);
