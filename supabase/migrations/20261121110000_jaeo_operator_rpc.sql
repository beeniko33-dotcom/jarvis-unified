-- Server-only RPC boundary for the authenticated JAEO Edge Function.
-- The private tables remain unexposed; only service_role may execute this function.
create or replace function public.jaeo_operator_api(
  p_operation text,
  p_user_id uuid,
  p_is_operator boolean,
  p_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_task jarvis_private.jaeo_tasks%rowtype;
  v_approval jarvis_private.jaeo_approvals%rowtype;
  v_feedback jarvis_private.jaeo_feedback%rowtype;
  v_id uuid;
  v_hash text;
  v_resource text;
  v_action text;
  v_decision text;
  v_rows jsonb;
begin
  if p_user_id is null or p_payload is null or jsonb_typeof(p_payload) <> 'object' then
    raise exception 'jaeo_invalid_api_request' using errcode = '22023';
  end if;

  if p_operation = 'create_task' then
    insert into jarvis_private.jaeo_tasks (
      idempotency_key, title, description, agent_role, workspace_scope,
      autonomy, feedback_mode, mode, live_trading_enabled, requested_by
    ) values (
      p_payload->>'idempotency_key', p_payload->>'title', p_payload->>'description',
      p_payload->>'agent_role', coalesce(p_payload->>'workspace_scope','all'),
      'supervised', 'both', 'supervised', false, p_user_id
    )
    on conflict (idempotency_key) do nothing
    returning * into v_task;

    if v_task.id is null then
      select * into v_task from jarvis_private.jaeo_tasks
      where idempotency_key = p_payload->>'idempotency_key';
      if v_task.id is null or v_task.requested_by is distinct from p_user_id then
        raise exception 'jaeo_idempotency_conflict' using errcode = '23505';
      end if;
      return jsonb_build_object('task', to_jsonb(v_task), 'duplicate', true);
    end if;
    return jsonb_build_object('task', to_jsonb(v_task), 'duplicate', false);

  elsif p_operation = 'list_tasks' then
    if p_is_operator then
      select coalesce(jsonb_agg(to_jsonb(q) order by q.created_at desc),'[]'::jsonb) into v_rows
      from (
        select id,title,description,agent_role,workspace_scope,autonomy,feedback_mode,mode,status,
               created_at,started_at,completed_at,result,requested_by
        from jarvis_private.jaeo_tasks order by created_at desc limit 50
      ) q;
    else
      select coalesce(jsonb_agg(to_jsonb(q) order by q.created_at desc),'[]'::jsonb) into v_rows
      from (
        select id,title,description,agent_role,workspace_scope,autonomy,feedback_mode,mode,status,
               created_at,started_at,completed_at,result,requested_by
        from jarvis_private.jaeo_tasks where requested_by = p_user_id
        order by created_at desc limit 50
      ) q;
    end if;
    return jsonb_build_object('tasks', coalesce(v_rows,'[]'::jsonb));

  elsif p_operation = 'request_approval' then
    v_action := p_payload->>'action';
    v_resource := btrim(p_payload->>'resource_id');
    v_hash := p_payload->>'request_hash';
    if v_action not in ('change_code','change_schema','change_secret','provision_resource','create_cron','deploy_preview','merge_pull_request')
       or v_resource = '' or length(v_resource) > 256
       or v_hash !~ '^[0-9a-f]{64}$'
       or v_resource = any(array['zythldptlplyutphgxpg','db.zythldptlplyutphgxpg.supabase.co','jarvis-control-worker','production','prod'])
       or lower(v_resource) like 'prod:%'
       or position('zythldptlplyutphgxpg' in lower(v_resource)) > 0 then
      raise exception 'jaeo_approval_request_denied' using errcode = '42501';
    end if;
    select * into v_task from jarvis_private.jaeo_tasks
      where id = (p_payload->>'task_id')::uuid and requested_by = p_user_id;
    if v_task.id is null then raise exception 'jaeo_task_not_found' using errcode = 'P0002'; end if;

    insert into jarvis_private.jaeo_approvals (
      task_id, action, resource_id, request, status, requested_by, request_hash
    ) values (
      v_task.id, v_action, v_resource, coalesce(p_payload->'request','{}'::jsonb),
      'pending', p_user_id, v_hash
    ) returning * into v_approval;
    return jsonb_build_object('approval', to_jsonb(v_approval),
      'note','Approval records authorization only; this API never executes the requested action.');

  elsif p_operation = 'decide_approval' then
    if not coalesce(p_is_operator,false) then
      raise exception 'jaeo_operator_role_required' using errcode = '42501';
    end if;
    v_decision := p_payload->>'decision';
    if v_decision not in ('approved','rejected') then
      raise exception 'jaeo_invalid_approval_decision' using errcode = '22023';
    end if;
    select * into v_approval from jarvis_private.jaeo_approvals
      where id = (p_payload->>'approval_id')::uuid for update;
    if v_approval.id is null then raise exception 'jaeo_approval_not_found' using errcode = 'P0002'; end if;
    if v_approval.status <> 'pending' or v_approval.expires_at <= now() then
      raise exception 'jaeo_approval_expired_or_decided' using errcode = '23514';
    end if;
    if v_approval.requested_by = p_user_id then
      raise exception 'jaeo_self_approval_denied' using errcode = '42501';
    end if;
    v_resource := lower(v_approval.resource_id);
    if v_resource = any(array['zythldptlplyutphgxpg','db.zythldptlplyutphgxpg.supabase.co','jarvis-control-worker','production','prod'])
       or v_resource like 'prod:%' or position('zythldptlplyutphgxpg' in v_resource) > 0 then
      raise exception 'jaeo_production_resource_denied' using errcode = '42501';
    end if;
    update jarvis_private.jaeo_approvals set
      status = v_decision, decided_at = now(), decided_by_user_id = p_user_id,
      decided_by = p_user_id::text,
      decision_reason = left(coalesce(p_payload->>'reason',''),1000)
    where id = v_approval.id and status = 'pending' and expires_at > now()
    returning * into v_approval;
    if v_approval.id is null then raise exception 'jaeo_approval_race_or_expiry' using errcode = '23514'; end if;
    return jsonb_build_object('approval',to_jsonb(v_approval),
      'note','Decision recorded; no external action was executed.');

  elsif p_operation = 'add_feedback' then
    select * into v_task from jarvis_private.jaeo_tasks
      where id = (p_payload->>'task_id')::uuid;
    if v_task.id is null or (v_task.requested_by <> p_user_id and not coalesce(p_is_operator,false)) then
      raise exception 'jaeo_task_not_found' using errcode = 'P0002';
    end if;
    insert into jarvis_private.jaeo_feedback(task_id,agent_role,status,payload)
    values (v_task.id,p_payload->>'agent_role',p_payload->>'status',p_payload->'payload')
    returning * into v_feedback;
    return jsonb_build_object('feedback',jsonb_build_object(
      'id',v_feedback.id,'task_id',v_feedback.task_id,'agent_role',v_feedback.agent_role,
      'status',v_feedback.status,'occurred_at',v_feedback.occurred_at));
  end if;

  raise exception 'jaeo_unsupported_operation' using errcode = '22023';
end;
$function$;

revoke all on function public.jaeo_operator_api(text,uuid,boolean,jsonb) from public, anon, authenticated;
grant execute on function public.jaeo_operator_api(text,uuid,boolean,jsonb) to service_role;
comment on function public.jaeo_operator_api(text,uuid,boolean,jsonb) is
  'Server-only JAEO API dispatcher. Edge Function must authenticate user and derive requester/operator claims; this RPC never executes approved actions.';
