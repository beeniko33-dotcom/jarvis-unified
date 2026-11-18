-- Read-only NikoCoin ledger history for the authenticated account Edge Function.
-- The private ledger itself remains unexposed; only service_role can call this RPC.
create or replace function public.jarvis_nikocoin_history(
  p_user_id uuid,
  p_limit integer default 50
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_entries jsonb;
  v_limit integer := least(greatest(coalesce(p_limit, 50), 1), 100);
begin
  if p_user_id is null then
    raise exception 'user_id_required' using errcode = '22023';
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', q.id,
        'entry_type', q.entry_type,
        'amount', q.amount,
        'unit', q.unit,
        'event_code', q.event_code,
        'created_at', q.created_at
      ) order by q.created_at desc
    ),
    '[]'::jsonb
  )
  into v_entries
  from (
    select l.id, l.entry_type, l.amount, l.unit, l.event_code, l.created_at
    from jarvis_private.nikocoin_ledger l
    where l.user_id = p_user_id
    order by l.created_at desc
    limit v_limit
  ) q;

  return jsonb_build_object(
    'entries', v_entries,
    'count', jsonb_array_length(v_entries),
    'unit', 'NIKO',
    'status', 'internal_reward_only',
    'on_chain', false,
    'cash_value', false,
    'transferable', false
  );
end;
$$;
revoke all on function public.jarvis_nikocoin_history(uuid,integer) from public, anon, authenticated;
grant execute on function public.jarvis_nikocoin_history(uuid,integer) to service_role;
comment on function public.jarvis_nikocoin_history(uuid,integer) is
  'Returns limited NikoCoin ledger history for a user. Service-role only; invoked by the JWT-authenticated account Edge Function.';
