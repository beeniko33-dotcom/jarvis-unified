-- Move marketplace order creation behind a JWT-authenticated Edge Function.
-- The database RPC is now callable only by service_role, with explicit buyer identity
-- supplied by the Edge Function after validating the user's bearer JWT.
alter table public.marketplace_orders
  add column if not exists idempotency_key uuid;
update public.marketplace_orders
   set idempotency_key = gen_random_uuid()
 where idempotency_key is null;
alter table public.marketplace_orders
  alter column idempotency_key set not null;
create unique index if not exists marketplace_orders_buyer_idempotency_uidx
  on public.marketplace_orders(buyer_id, idempotency_key);
grant select, insert, update on public.marketplace_orders to service_role;

revoke all on function public.marketplace_create_order(uuid,integer,text)
  from public, anon, authenticated;

create or replace function public.marketplace_create_order_for_user(
  p_buyer_id uuid,
  p_listing_id uuid,
  p_quantity integer,
  p_affiliate_code text,
  p_idempotency_key uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_listing record;
  v_affiliate uuid := null;
  v_order_id uuid;
  v_total numeric(16,2);
  v_duplicate boolean := false;
  v_existing record;
begin
  if p_buyer_id is null or not exists(select 1 from auth.users u where u.id=p_buyer_id) then
    raise exception 'buyer_not_found' using errcode = '28000';
  end if;
  if p_idempotency_key is null then
    raise exception 'idempotency_key_required' using errcode = '22023';
  end if;
  if p_quantity is null or p_quantity < 1 or p_quantity > 1000 then
    raise exception 'invalid_quantity' using errcode = '22023';
  end if;

  select o.id,o.listing_id,o.quantity,o.affiliate_link_id,o.status,o.unit_price,o.currency
    into v_existing
    from public.marketplace_orders o
   where o.buyer_id=p_buyer_id and o.idempotency_key=p_idempotency_key
   for update;
  if found then
    if v_existing.listing_id <> p_listing_id or v_existing.quantity <> p_quantity then
      raise exception 'idempotency_key_reused_with_different_order' using errcode = '22023';
    end if;
    return jsonb_build_object(
      'order_id',v_existing.id,'status',v_existing.status,'quantity',v_existing.quantity,
      'unit_price',v_existing.unit_price,'total',v_existing.unit_price*v_existing.quantity,
      'currency',v_existing.currency,'payment_status','not_started',
      'reward_status','not_issued','duplicate',true
    );
  end if;

  select l.id,l.seller_id,l.price,l.currency,s.owner_id
    into v_listing
    from public.marketplace_listings l
    join public.marketplace_sellers s on s.id=l.seller_id
   where l.id=p_listing_id and l.status='published'
     and s.verification_status='verified'
   for share of l,s;
  if not found then raise exception 'listing_unavailable' using errcode = 'P0002'; end if;
  if v_listing.owner_id=p_buyer_id then
    raise exception 'seller_cannot_buy_own_listing' using errcode = '42501';
  end if;

  if p_affiliate_code is not null then
    select a.id into v_affiliate
      from public.marketplace_affiliate_links a
     where a.code=p_affiliate_code
       and a.listing_id=p_listing_id
       and a.status='active'
       and a.affiliate_user_id<>p_buyer_id
     limit 1;
    if v_affiliate is null then
      raise exception 'invalid_or_self_referred_affiliate_code' using errcode = '22023';
    end if;
  end if;

  v_total := v_listing.price*p_quantity;
  insert into public.marketplace_orders(
    buyer_id,seller_id,listing_id,affiliate_link_id,idempotency_key,
    quantity,unit_price,currency,status
  ) values (
    p_buyer_id,v_listing.seller_id,v_listing.id,v_affiliate,p_idempotency_key,
    p_quantity,v_listing.price,v_listing.currency,'created'
  )
  on conflict (buyer_id,idempotency_key) do nothing
  returning id into v_order_id;

  if v_order_id is null then
    select o.id,o.listing_id,o.quantity,o.affiliate_link_id,o.status,o.unit_price,o.currency
      into v_existing from public.marketplace_orders o
     where o.buyer_id=p_buyer_id and o.idempotency_key=p_idempotency_key;
    if v_existing.listing_id<>p_listing_id or v_existing.quantity<>p_quantity then
      raise exception 'idempotency_key_reused_with_different_order' using errcode = '22023';
    end if;
    v_order_id:=v_existing.id;
    v_duplicate:=true;
    v_total:=v_existing.unit_price*v_existing.quantity;
  end if;

  return jsonb_build_object(
    'order_id',v_order_id,'status','created','quantity',p_quantity,
    'unit_price',v_listing.price,'total',v_total,'currency',v_listing.currency,
    'payment_status','not_started','reward_status','not_issued','duplicate',v_duplicate
  );
end;
$$;
revoke all on function public.marketplace_create_order_for_user(uuid,uuid,integer,text,uuid)
  from public,anon,authenticated;
grant execute on function public.marketplace_create_order_for_user(uuid,uuid,integer,text,uuid)
  to service_role;
comment on function public.marketplace_create_order_for_user(uuid,uuid,integer,text,uuid) is
  'Service-role-only idempotent marketplace order-intent RPC. Called only after the JWT-authenticated marketplace-orders Edge Function derives the buyer ID.';
