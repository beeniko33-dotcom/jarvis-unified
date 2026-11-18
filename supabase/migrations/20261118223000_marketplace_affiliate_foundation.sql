-- Marketplace foundation: seller onboarding, listings, affiliate links and safe order intents.
-- This migration intentionally does not process payments or issue NikoCoin rewards.
create table public.marketplace_sellers (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete restrict,
  display_name text not null check (length(trim(display_name)) between 2 and 120),
  description text check (description is null or length(description) <= 4000),
  country_code text check (country_code is null or country_code ~ '^[A-Z]{2}$'),
  verification_status text not null default 'pending'
    check (verification_status in ('pending','verified','rejected','suspended')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index marketplace_sellers_owner_idx on public.marketplace_sellers(owner_id);
alter table public.marketplace_sellers enable row level security;
create policy marketplace_sellers_read on public.marketplace_sellers
  for select to authenticated
  using (owner_id = auth.uid() or verification_status = 'verified');
create policy marketplace_sellers_create on public.marketplace_sellers
  for insert to authenticated
  with check (owner_id = auth.uid() and verification_status = 'pending');
create policy marketplace_sellers_update on public.marketplace_sellers
  for update to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());
revoke all on public.marketplace_sellers from anon;
grant select, insert on public.marketplace_sellers to authenticated;
grant update(display_name, description, country_code) on public.marketplace_sellers to authenticated;

create table public.marketplace_listings (
  id uuid primary key default gen_random_uuid(),
  seller_id uuid not null references public.marketplace_sellers(id) on delete restrict,
  created_by uuid not null references auth.users(id) on delete restrict,
  title text not null check (length(trim(title)) between 3 and 180),
  description text not null check (length(trim(description)) between 20 and 12000),
  listing_type text not null check (listing_type in ('physical','digital','service')),
  price numeric(14,2) not null check (price >= 0),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  status text not null default 'draft' check (status in ('draft','published','archived')),
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status <> 'published' or published_at is not null)
);
create index marketplace_listings_public_idx on public.marketplace_listings(status, created_at desc);
create index marketplace_listings_seller_idx on public.marketplace_listings(seller_id, created_at desc);
alter table public.marketplace_listings enable row level security;
create policy marketplace_listings_read on public.marketplace_listings
  for select to authenticated
  using (
    (status = 'published' and exists (
      select 1 from public.marketplace_sellers s
      where s.id = seller_id and s.verification_status = 'verified'
    ))
    or exists (select 1 from public.marketplace_sellers s
      where s.id = seller_id and s.owner_id = auth.uid())
  );
create policy marketplace_listings_create on public.marketplace_listings
  for insert to authenticated
  with check (
    created_by = auth.uid() and status = 'draft' and exists (
      select 1 from public.marketplace_sellers s
      where s.id = seller_id and s.owner_id = auth.uid()
        and s.verification_status = 'verified'
    )
  );
create policy marketplace_listings_update on public.marketplace_listings
  for update to authenticated
  using (exists (select 1 from public.marketplace_sellers s
    where s.id = seller_id and s.owner_id = auth.uid()))
  with check (
    exists (select 1 from public.marketplace_sellers s
      where s.id = seller_id and s.owner_id = auth.uid()
        and (status <> 'published' or s.verification_status = 'verified'))
  );
revoke all on public.marketplace_listings from anon;
grant select, insert on public.marketplace_listings to authenticated;
grant update(title, description, listing_type, price, currency, status, published_at)
  on public.marketplace_listings to authenticated;

create table public.marketplace_affiliate_links (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.marketplace_listings(id) on delete cascade,
  affiliate_user_id uuid not null references auth.users(id) on delete restrict,
  code text not null unique default replace(gen_random_uuid()::text, '-', ''),
  status text not null default 'active' check (status in ('active','disabled')),
  created_at timestamptz not null default now(),
  unique(listing_id, affiliate_user_id)
);
create index marketplace_affiliate_listing_idx on public.marketplace_affiliate_links(listing_id);
alter table public.marketplace_affiliate_links enable row level security;
create policy marketplace_affiliate_links_read on public.marketplace_affiliate_links
  for select to authenticated using (affiliate_user_id = auth.uid());
create policy marketplace_affiliate_links_create on public.marketplace_affiliate_links
  for insert to authenticated
  with check (
    affiliate_user_id = auth.uid()
    and exists (select 1 from public.marketplace_listings l
      join public.marketplace_sellers s on s.id = l.seller_id
      where l.id = listing_id and l.status = 'published'
        and s.verification_status = 'verified' and s.owner_id <> auth.uid())
  );
revoke all on public.marketplace_affiliate_links from anon;
grant select on public.marketplace_affiliate_links to authenticated;
grant insert(listing_id, affiliate_user_id) on public.marketplace_affiliate_links to authenticated;

create table public.marketplace_orders (
  id uuid primary key default gen_random_uuid(),
  buyer_id uuid not null references auth.users(id) on delete restrict,
  seller_id uuid not null references public.marketplace_sellers(id) on delete restrict,
  listing_id uuid not null references public.marketplace_listings(id) on delete restrict,
  affiliate_link_id uuid references public.marketplace_affiliate_links(id) on delete set null,
  quantity integer not null check (quantity between 1 and 1000),
  unit_price numeric(14,2) not null check (unit_price >= 0),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  status text not null default 'created'
    check (status in ('created','cancelled','fulfilled','refunded')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index marketplace_orders_buyer_idx on public.marketplace_orders(buyer_id, created_at desc);
create index marketplace_orders_seller_idx on public.marketplace_orders(seller_id, created_at desc);
alter table public.marketplace_orders enable row level security;
create policy marketplace_orders_participant_read on public.marketplace_orders
  for select to authenticated
  using (
    buyer_id = auth.uid()
    or exists (select 1 from public.marketplace_sellers s
      where s.id = seller_id and s.owner_id = auth.uid())
  );
revoke all on public.marketplace_orders from anon, authenticated;
grant select on public.marketplace_orders to authenticated;

-- A trusted database function snapshots price from the published listing.
-- The browser cannot supply or alter order totals/status or mark an order paid.
create or replace function public.marketplace_create_order(
  p_listing_id uuid,
  p_quantity integer,
  p_affiliate_code text default null
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
  v_listing record;
  v_affiliate uuid := null;
  v_order_id uuid;
  v_total numeric(16,2);
begin
  if v_user is null then
    raise exception 'authentication_required' using errcode = '28000';
  end if;
  if p_quantity is null or p_quantity < 1 or p_quantity > 1000 then
    raise exception 'invalid_quantity' using errcode = '22023';
  end if;

  select l.id, l.seller_id, l.price, l.currency, s.owner_id
    into v_listing
    from public.marketplace_listings l
    join public.marketplace_sellers s on s.id = l.seller_id
   where l.id = p_listing_id
     and l.status = 'published'
     and s.verification_status = 'verified'
   for share of l, s;
  if not found then
    raise exception 'listing_unavailable' using errcode = 'P0002';
  end if;
  if v_listing.owner_id = v_user then
    raise exception 'seller_cannot_buy_own_listing' using errcode = '42501';
  end if;

  if p_affiliate_code is not null then
    select a.id into v_affiliate
      from public.marketplace_affiliate_links a
     where a.code = p_affiliate_code
       and a.listing_id = p_listing_id
       and a.status = 'active'
       and a.affiliate_user_id <> v_user
     limit 1;
  end if;

  v_total := v_listing.price * p_quantity;
  insert into public.marketplace_orders(
    buyer_id, seller_id, listing_id, affiliate_link_id,
    quantity, unit_price, currency, status
  ) values (
    v_user, v_listing.seller_id, v_listing.id, v_affiliate,
    p_quantity, v_listing.price, v_listing.currency, 'created'
  ) returning id into v_order_id;

  return jsonb_build_object(
    'order_id', v_order_id,
    'status', 'created',
    'quantity', p_quantity,
    'unit_price', v_listing.price,
    'total', v_total,
    'currency', v_listing.currency,
    'payment_status', 'not_started',
    'reward_status', 'not_issued'
  );
end;
$$;
revoke all on function public.marketplace_create_order(uuid, integer, text) from public, anon;
grant execute on function public.marketplace_create_order(uuid, integer, text) to authenticated;

comment on table public.marketplace_sellers is 'Seller onboarding. Verification is a trusted administrative decision; no identity documents are stored here.';
comment on table public.marketplace_listings is 'Marketplace catalogue. Only verified sellers can publish listings.';
comment on table public.marketplace_affiliate_links is 'Affiliate attribution links. Commission rules and reward issuance are not active in this foundation.';
comment on table public.marketplace_orders is 'Order intents only. No payment processing, payment credentials, or fulfillment automation is implemented.';
comment on function public.marketplace_create_order(uuid, integer, text) is 'Creates an authenticated order intent using a server-side price snapshot. Does not charge, settle, fulfill, or award rewards.';
