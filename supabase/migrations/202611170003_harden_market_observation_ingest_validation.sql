-- Defense-in-depth: reject missing values_json explicitly instead of allowing SQL NULL logic.
create or replace function public.jarvis_ingest_market_observations(p_observations jsonb)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare item jsonb; inserted_id uuid; inserted_count integer:=0; duplicate_count integer:=0;
ids jsonb:='[]'::jsonb; event_ts timestamptz; received_ts timestamptz;
symbol_value text; timeframe_value text; source_value text; hash_value text;
begin
 if jsonb_typeof(p_observations)<>'array' or jsonb_array_length(p_observations)<1 or jsonb_array_length(p_observations)>100 then
  raise exception 'observations must be an array containing 1 to 100 items'; end if;
 for item in select value from jsonb_array_elements(p_observations) loop
  if jsonb_typeof(item)<>'object' then raise exception 'each observation must be an object'; end if;
  symbol_value:=item->>'symbol'; timeframe_value:=item->>'timeframe'; source_value:=item->>'source_id'; hash_value:=item->>'content_hash';
  if coalesce(length(trim(symbol_value)),0) not between 1 and 64
   or coalesce(length(trim(timeframe_value)),0) not between 1 and 32
   or coalesce(length(trim(source_value)),0) not between 1 and 128
   or coalesce(hash_value,'') !~ '^[0-9a-f]{64}$'
   or coalesce(item->>'schema_version','') !~ '^[1-9][0-9]*$'
   or coalesce(item->>'event_time','')=''
   or coalesce(item->>'received_at','')=''
   or coalesce(jsonb_typeof(item->'values_json'),'')<>'object' then raise exception 'observation schema validation failed'; end if;
  event_ts:=(item->>'event_time')::timestamptz; received_ts:=(item->>'received_at')::timestamptz;
  insert into jarvis_private.market_observations(source_id,event_time,received_at,symbol,timeframe,schema_version,content_hash,values_json,out_of_order,stale,clock_skew,provenance)
  values(source_value,event_ts,received_ts,symbol_value,timeframe_value,(item->>'schema_version')::integer,hash_value,item->'values_json',
   coalesce((item->>'out_of_order')::boolean,false),coalesce((item->>'stale')::boolean,false),coalesce((item->>'clock_skew')::boolean,false),'candidate_unverified')
  on conflict(source_id,content_hash) do nothing returning id into inserted_id;
  if inserted_id is null then duplicate_count:=duplicate_count+1; else inserted_count:=inserted_count+1; ids:=ids||jsonb_build_array(inserted_id); end if;
  inserted_id:=null;
 end loop;
 return jsonb_build_object('inserted',inserted_count,'duplicates',duplicate_count,'observation_ids',ids,'provenance','candidate_unverified','evidence_credit',false);
end; $$;
revoke all on function public.jarvis_ingest_market_observations(jsonb) from public,anon,authenticated;
grant execute on function public.jarvis_ingest_market_observations(jsonb) to service_role;
