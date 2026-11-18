-- Source-control mirror of the index already applied to Supabase on 2026-11-18.
-- This file is for migration history reconciliation only; do not reapply to the live project.
create index if not exists market_signals_provider_observation_id_idx
    on jarvis_private.market_signals (provider_observation_id);
