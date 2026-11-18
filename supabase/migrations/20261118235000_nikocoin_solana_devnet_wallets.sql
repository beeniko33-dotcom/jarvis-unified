-- Solana Devnet wallet proof-of-control only. No token minting or transfers.
create table jarvis_private.nikocoin_wallet_challenges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  nonce text not null check (nonce ~ '^[0-9a-f]{64}$'),
  message text not null check (length(message) between 80 and 1200),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id, nonce),
  check (expires_at > created_at and expires_at <= created_at + interval '5 minutes')
);
create index nikocoin_wallet_challenges_user_idx
  on jarvis_private.nikocoin_wallet_challenges(user_id, created_at desc);

create table jarvis_private.nikocoin_wallets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  wallet_address text not null check (wallet_address ~ '^[1-9A-HJ-NP-Za-km-z]{32,44}$'),
  network text not null default 'devnet' check (network = 'devnet'),
  signature_hash text not null check (signature_hash ~ '^[0-9a-f]{64}$'),
  verified_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(user_id, network),
  unique(wallet_address, network)
);
alter table jarvis_private.nikocoin_wallet_challenges enable row level security;
alter table jarvis_private.nikocoin_wallets enable row level security;
revoke all on jarvis_private.nikocoin_wallet_challenges from public, anon, authenticated;
revoke all on jarvis_private.nikocoin_wallets from public, anon, authenticated;
grant select, insert, update, delete on jarvis_private.nikocoin_wallet_challenges to service_role;
grant select, insert, update on jarvis_private.nikocoin_wallets to service_role;

create or replace function public.jarvis_solana_create_wallet_challenge(
  p_user_id uuid, p_nonce text, p_message text, p_expires_at timestamptz
) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare v_id uuid;
begin
  if p_user_id is null or p_nonce !~ '^[0-9a-f]{64}$'
     or p_message is null or length(p_message) < 80 or length(p_message) > 1200
     or p_expires_at <= now() or p_expires_at > now() + interval '5 minutes' then
    raise exception 'invalid_wallet_challenge' using errcode = '22023';
  end if;
  insert into jarvis_private.nikocoin_wallet_challenges(user_id,nonce,message,expires_at)
  values(p_user_id,p_nonce,p_message,p_expires_at) returning id into v_id;
  return jsonb_build_object('challenge_id',v_id,'message',p_message,'expires_at',p_expires_at);
end;
$$;

create or replace function public.jarvis_solana_get_wallet_challenge(
  p_user_id uuid, p_challenge_id uuid, p_nonce text
) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare v_row record;
begin
  select id,user_id,nonce,message,expires_at,consumed_at
    into v_row from jarvis_private.nikocoin_wallet_challenges
   where id=p_challenge_id and user_id=p_user_id and nonce=p_nonce;
  if not found then raise exception 'wallet_challenge_not_found' using errcode = 'P0002'; end if;
  return jsonb_build_object('challenge_id',v_row.id,'message',v_row.message,
    'expires_at',v_row.expires_at,'consumed_at',v_row.consumed_at);
end;
$$;

create or replace function public.jarvis_solana_complete_wallet_link(
  p_user_id uuid, p_challenge_id uuid, p_nonce text,
  p_wallet_address text, p_signature_hash text
) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare v_challenge record; v_wallet_id uuid;
begin
  if p_user_id is null or p_wallet_address !~ '^[1-9A-HJ-NP-Za-km-z]{32,44}$'
     or p_signature_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_wallet_proof' using errcode = '22023';
  end if;
  select id,user_id,nonce,expires_at,consumed_at into v_challenge
    from jarvis_private.nikocoin_wallet_challenges
   where id=p_challenge_id and user_id=p_user_id and nonce=p_nonce
   for update;
  if not found or v_challenge.consumed_at is not null or v_challenge.expires_at <= now() then
    raise exception 'wallet_challenge_expired_or_used' using errcode = '42501';
  end if;
  update jarvis_private.nikocoin_wallet_challenges set consumed_at=now() where id=p_challenge_id;
  insert into jarvis_private.nikocoin_wallets(user_id,wallet_address,network,signature_hash)
  values(p_user_id,p_wallet_address,'devnet',p_signature_hash)
  on conflict(user_id,network) do update
    set wallet_address=excluded.wallet_address,
        signature_hash=excluded.signature_hash,
        verified_at=now()
  returning id into v_wallet_id;
  return jsonb_build_object('wallet_id',v_wallet_id,'wallet_address',p_wallet_address,
    'network','devnet','verified',true,'transfers_enabled',false,'token_mint_enabled',false);
end;
$$;

create or replace function public.jarvis_solana_get_wallet(p_user_id uuid)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare v_wallet record;
begin
  if p_user_id is null then raise exception 'user_id_required' using errcode = '22023'; end if;
  select wallet_address,network,verified_at into v_wallet
    from jarvis_private.nikocoin_wallets where user_id=p_user_id and network='devnet';
  if not found then return jsonb_build_object('linked',false,'network','devnet',
    'transfers_enabled',false,'token_mint_enabled',false); end if;
  return jsonb_build_object('linked',true,'wallet_address',v_wallet.wallet_address,
    'network',v_wallet.network,'verified_at',v_wallet.verified_at,
    'transfers_enabled',false,'token_mint_enabled',false);
end;
$$;

revoke all on function public.jarvis_solana_create_wallet_challenge(uuid,text,text,timestamptz) from public,anon,authenticated;
revoke all on function public.jarvis_solana_get_wallet_challenge(uuid,uuid,text) from public,anon,authenticated;
revoke all on function public.jarvis_solana_complete_wallet_link(uuid,uuid,text,text,text) from public,anon,authenticated;
revoke all on function public.jarvis_solana_get_wallet(uuid) from public,anon,authenticated;
grant execute on function public.jarvis_solana_create_wallet_challenge(uuid,text,text,timestamptz) to service_role;
grant execute on function public.jarvis_solana_get_wallet_challenge(uuid,uuid,text) to service_role;
grant execute on function public.jarvis_solana_complete_wallet_link(uuid,uuid,text,text,text) to service_role;
grant execute on function public.jarvis_solana_get_wallet(uuid) to service_role;

comment on table jarvis_private.nikocoin_wallets is 'Verified Solana Devnet public wallet addresses only. No private keys, signing authority, token balances, or transfers.';
comment on table jarvis_private.nikocoin_wallet_challenges is 'Short-lived one-time wallet proof challenges. Service-role only.';
