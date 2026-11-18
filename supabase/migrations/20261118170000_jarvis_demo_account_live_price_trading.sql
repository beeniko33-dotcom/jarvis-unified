-- Persistent demo account and live-price paper trading. No exchange credentials or live order routes.
create table if not exists jarvis_private.demo_accounts (
  user_id uuid primary key references auth.users(id) on delete restrict,
  currency text not null default 'USDT' check (currency = 'USDT'),
  starting_balance numeric(24,8) not null default 10000 check (starting_balance > 0),
  cash_balance numeric(24,8) not null default 10000 check (cash_balance >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists jarvis_private.demo_positions (
  user_id uuid not null references jarvis_private.demo_accounts(user_id) on delete cascade,
  symbol text not null check (symbol in ('BTCUSDT','ETHUSDT','SOLUSDT')),
  quantity numeric(24,8) not null check (quantity > 0),
  average_entry_price numeric(24,8) not null check (average_entry_price > 0),
  updated_at timestamptz not null default now(),
  primary key (user_id, symbol)
);
create table if not exists jarvis_private.demo_orders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references jarvis_private.demo_accounts(user_id) on delete restrict,
  idempotency_key uuid not null,
  symbol text not null check (symbol in ('BTCUSDT','ETHUSDT','SOLUSDT')),
  side text not null check (side in ('buy','sell')),
  quantity numeric(24,8) not null check (quantity > 0),
  execution_price numeric(24,8) not null check (execution_price > 0),
  notional numeric(24,8) not null check (notional > 0),
  fee numeric(24,8) not null check (fee >= 0),
  provider text not null check (provider = 'Binance Spot'),
  provider_timestamp timestamptz not null,
  created_at timestamptz not null default now(),
  status text not null default 'filled' check (status = 'filled'),
  unique (user_id, idempotency_key)
);
create index if not exists demo_orders_user_created_idx on jarvis_private.demo_orders(user_id, created_at desc);
alter table jarvis_private.demo_accounts enable row level security;
alter table jarvis_private.demo_positions enable row level security;
alter table jarvis_private.demo_orders enable row level security;
revoke all on jarvis_private.demo_accounts, jarvis_private.demo_positions, jarvis_private.demo_orders from public, anon, authenticated;
grant select, insert, update, delete on jarvis_private.demo_accounts, jarvis_private.demo_positions, jarvis_private.demo_orders to service_role;

create or replace function public.jarvis_demo_account_snapshot(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare v_account jsonb; v_positions jsonb; v_orders jsonb;
begin
  if not exists (select 1 from public.operator_allowlist a where a.user_id = p_user_id) then
    raise exception 'operator_not_allowlisted';
  end if;
  insert into jarvis_private.demo_accounts(user_id) values (p_user_id) on conflict (user_id) do nothing;
  select jsonb_build_object('user_id',user_id,'currency',currency,'starting_balance',starting_balance,
    'cash_balance',cash_balance,'created_at',created_at,'updated_at',updated_at)
    into v_account from jarvis_private.demo_accounts where user_id=p_user_id;
  select coalesce(jsonb_agg(jsonb_build_object('symbol',symbol,'quantity',quantity,
    'average_entry_price',average_entry_price,'updated_at',updated_at) order by symbol),'[]'::jsonb)
    into v_positions from jarvis_private.demo_positions where user_id=p_user_id;
  select coalesce(jsonb_agg(jsonb_build_object('id',id,'symbol',symbol,'side',side,'quantity',quantity,
    'execution_price',execution_price,'notional',notional,'fee',fee,'provider',provider,
    'provider_timestamp',provider_timestamp,'created_at',created_at,'status',status)
    order by created_at desc),'[]'::jsonb)
    into v_orders from (select * from jarvis_private.demo_orders where user_id=p_user_id
      order by created_at desc limit 50) q;
  return jsonb_build_object('account',v_account,'positions',v_positions,'orders',v_orders,
    'account_type','demo','execution_mode','paper','live_orders',0);
end;
$$;

create or replace function public.jarvis_execute_demo_trade(
  p_user_id uuid, p_symbol text, p_side text, p_quantity numeric, p_price numeric,
  p_provider_timestamp timestamptz, p_idempotency_key uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_account jarvis_private.demo_accounts%rowtype;
  v_position jarvis_private.demo_positions%rowtype;
  v_existing jarvis_private.demo_orders%rowtype;
  v_notional numeric(24,8); v_fee numeric(24,8); v_new_qty numeric(24,8);
  v_new_avg numeric(24,8); v_order_id uuid;
begin
  if not exists (select 1 from public.operator_allowlist a where a.user_id=p_user_id) then raise exception 'operator_not_allowlisted'; end if;
  if p_symbol not in ('BTCUSDT','ETHUSDT','SOLUSDT') or p_side not in ('buy','sell') then raise exception 'unsupported_market_or_side'; end if;
  if p_quantity is null or p_quantity <= 0 or p_quantity > 100000 then raise exception 'invalid_quantity'; end if;
  if p_price is null or p_price <= 0 or p_price > 1000000000 then raise exception 'invalid_market_price'; end if;
  if p_provider_timestamp is null or abs(extract(epoch from (clock_timestamp()-p_provider_timestamp))) > 30 then raise exception 'market_price_stale'; end if;
  if p_idempotency_key is null then raise exception 'idempotency_key_required'; end if;

  insert into jarvis_private.demo_accounts(user_id) values (p_user_id) on conflict (user_id) do nothing;
  select * into v_account from jarvis_private.demo_accounts where user_id=p_user_id for update;
  select * into v_existing from jarvis_private.demo_orders where user_id=p_user_id and idempotency_key=p_idempotency_key;
  if found then return jsonb_build_object('duplicate',true,'order_id',v_existing.id,'status',v_existing.status); end if;

  v_notional := round(p_quantity*p_price,8);
  v_fee := round(v_notional*0.001,8);
  if v_notional > v_account.starting_balance*0.25 then raise exception 'per_trade_notional_limit_exceeded'; end if;

  if p_side='buy' then
    if v_notional+v_fee > v_account.cash_balance then raise exception 'insufficient_demo_cash'; end if;
    update jarvis_private.demo_accounts set cash_balance=cash_balance-v_notional-v_fee,updated_at=now() where user_id=p_user_id;
    select * into v_position from jarvis_private.demo_positions where user_id=p_user_id and symbol=p_symbol for update;
    if found then
      v_new_qty:=v_position.quantity+p_quantity;
      v_new_avg:=((v_position.quantity*v_position.average_entry_price)+v_notional)/v_new_qty;
      update jarvis_private.demo_positions set quantity=v_new_qty,average_entry_price=v_new_avg,updated_at=now()
        where user_id=p_user_id and symbol=p_symbol;
    else
      insert into jarvis_private.demo_positions(user_id,symbol,quantity,average_entry_price)
        values(p_user_id,p_symbol,p_quantity,p_price);
    end if;
  else
    select * into v_position from jarvis_private.demo_positions where user_id=p_user_id and symbol=p_symbol for update;
    if not found or v_position.quantity < p_quantity then raise exception 'insufficient_demo_position'; end if;
    update jarvis_private.demo_accounts set cash_balance=cash_balance+v_notional-v_fee,updated_at=now() where user_id=p_user_id;
    if v_position.quantity=p_quantity then
      delete from jarvis_private.demo_positions where user_id=p_user_id and symbol=p_symbol;
    else
      update jarvis_private.demo_positions set quantity=quantity-p_quantity,updated_at=now()
        where user_id=p_user_id and symbol=p_symbol;
    end if;
  end if;

  insert into jarvis_private.demo_orders(user_id,idempotency_key,symbol,side,quantity,execution_price,notional,fee,provider,provider_timestamp)
    values(p_user_id,p_idempotency_key,p_symbol,p_side,p_quantity,p_price,v_notional,v_fee,'Binance Spot',p_provider_timestamp)
    returning id into v_order_id;
  return jsonb_build_object('duplicate',false,'order_id',v_order_id,'status','filled','symbol',p_symbol,
    'side',p_side,'quantity',p_quantity,'execution_price',p_price,'notional',v_notional,'fee',v_fee,
    'provider','Binance Spot','provider_timestamp',p_provider_timestamp,'execution_mode','paper','live_orders',0);
end;
$$;
revoke all on function public.jarvis_demo_account_snapshot(uuid) from public, anon, authenticated;
revoke all on function public.jarvis_execute_demo_trade(uuid,text,text,numeric,numeric,timestamptz,uuid) from public, anon, authenticated;
grant execute on function public.jarvis_demo_account_snapshot(uuid) to service_role;
grant execute on function public.jarvis_execute_demo_trade(uuid,text,text,numeric,numeric,timestamptz,uuid) to service_role;
comment on schema jarvis_private is 'Private Jarvis ledgers; demo account/order data is simulated and never routes to a live exchange.';
