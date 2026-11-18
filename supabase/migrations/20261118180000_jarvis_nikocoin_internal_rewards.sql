-- NikoCoin internal rewards ledger. This is NOT an SPL token and has no cash value.
-- Award only from trusted server-side workflows after independently validating the qualifying event.
create table if not exists jarvis_private.nikocoin_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  entry_type text not null check (entry_type in ('credit','debit','reversal')),
  amount numeric(20,4) not null check (amount > 0),
  unit text not null default 'NIKO' check (unit = 'NIKO'),
  event_code text not null check (event_code ~ '^[a-z][a-z0-9_]{1,63}$'),
  idempotency_key uuid not null,
  source_reference text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);
create index if not exists nikocoin_ledger_user_created_idx
  on jarvis_private.nikocoin_ledger(user_id, created_at desc);
alter table jarvis_private.nikocoin_ledger enable row level security;
revoke all on jarvis_private.nikocoin_ledger from public, anon, authenticated;
grant select, insert on jarvis_private.nikocoin_ledger to service_role;

-- Ledger rows are immutable. Corrections must be new compensating entries.
create or replace function jarvis_private.reject_nikocoin_ledger_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'nikocoin_ledger_is_append_only';
end;
$$;
drop trigger if exists nikocoin_ledger_no_mutation on jarvis_private.nikocoin_ledger;
create trigger nikocoin_ledger_no_mutation
before update or delete on jarvis_private.nikocoin_ledger
for each row execute function jarvis_private.reject_nikocoin_ledger_mutation();
revoke all on function jarvis_private.reject_nikocoin_ledger_mutation() from public, anon, authenticated;

-- Service-role-only credit entry point. Callers must validate event eligibility before invoking.
create or replace function public.jarvis_nikocoin_award(
  p_user_id uuid,
  p_amount numeric,
  p_event_code text,
  p_idempotency_key uuid,
  p_source_reference text default null,
  p_metadata jsonb default '{}'::jsonb
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_entry_id uuid; v_balance numeric(20,4);
begin
  if p_user_id is null or not exists (select 1 from auth.users u where u.id=p_user_id) then
    raise exception 'nikocoin_user_not_found';
  end if;
  if p_amount is null or p_amount <= 0 or p_amount > 100000 then
    raise exception 'nikocoin_amount_out_of_range';
  end if;
  if p_event_code is null or p_event_code !~ '^[a-z][a-z0-9_]{1,63}$' then
    raise exception 'nikocoin_invalid_event_code';
  end if;
  if p_idempotency_key is null then raise exception 'nikocoin_idempotency_required'; end if;
  if p_metadata is null or jsonb_typeof(p_metadata) <> 'object' then
    raise exception 'nikocoin_metadata_must_be_object';
  end if;

  insert into jarvis_private.nikocoin_ledger
    (user_id,entry_type,amount,event_code,idempotency_key,source_reference,metadata)
  values
    (p_user_id,'credit',p_amount,p_event_code,p_idempotency_key,p_source_reference,p_metadata)
  on conflict (user_id,idempotency_key) do nothing
  returning id into v_entry_id;

  select coalesce(sum(case when entry_type='credit' then amount else -amount end),0)
    into v_balance
    from jarvis_private.nikocoin_ledger where user_id=p_user_id;

  return jsonb_build_object(
    'credited', v_entry_id is not null,
    'duplicate', v_entry_id is null,
    'entry_id', v_entry_id,
    'user_id', p_user_id,
    'unit', 'NIKO',
    'balance', v_balance,
    'status', 'internal_reward_only',
    'transferable', false,
    'cash_value', false,
    'on_chain', false
  );
end;
$$;
revoke all on function public.jarvis_nikocoin_award(uuid,numeric,text,uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.jarvis_nikocoin_award(uuid,numeric,text,uuid,text,jsonb) to service_role;

-- Read-only balance snapshot; exposed only to trusted server code, not browser clients.
create or replace function public.jarvis_nikocoin_balance(p_user_id uuid)
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'user_id', p_user_id,
    'unit', 'NIKO',
    'balance', coalesce(sum(case when entry_type='credit' then amount else -amount end),0),
    'status', 'internal_reward_only',
    'transferable', false,
    'cash_value', false,
    'on_chain', false
  )
  from jarvis_private.nikocoin_ledger
  where user_id=p_user_id;
$$;
revoke all on function public.jarvis_nikocoin_balance(uuid) from public, anon, authenticated;
grant execute on function public.jarvis_nikocoin_balance(uuid) to service_role;

comment on table jarvis_private.nikocoin_ledger is
  'Append-only internal NikoCoin rewards ledger. Not an SPL token, not transferable, and has no cash value.';
comment on function public.jarvis_nikocoin_award(uuid,numeric,text,uuid,text,jsonb) is
  'Trusted server-side award primitive only. Caller must validate the earning event and enforce business reward rules before invoking.';
