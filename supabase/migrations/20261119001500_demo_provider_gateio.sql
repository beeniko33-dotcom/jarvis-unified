-- Preserve historical Binance-labelled demo rows while recording new Gate.io marks accurately.
alter table jarvis_private.demo_orders
  drop constraint if exists demo_orders_provider_check;

alter table jarvis_private.demo_orders
  add constraint demo_orders_provider_check
  check (provider in ('Binance Spot', 'Gate.io Spot'));

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
    values(p_user_id,p_idempotency_key,p_symbol,p_side,p_quantity,p_price,v_notional,v_fee,'Gate.io Spot',p_provider_timestamp)
    returning id into v_order_id;
  return jsonb_build_object('duplicate',false,'order_id',v_order_id,'status','filled','symbol',p_symbol,
    'side',p_side,'quantity',p_quantity,'execution_price',p_price,'notional',v_notional,'fee',v_fee,
    'provider','Gate.io Spot','provider_timestamp',p_provider_timestamp,'execution_mode','paper','live_orders',0);
end;
$$;
