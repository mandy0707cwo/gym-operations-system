-- v1.13.19：只新增操作收據，不回寫歷史交易、不改財務公式。
-- 受控私有 DEFINER 僅處理本人操作；public 入口保持 INVOKER。
-- 防止對不同財務／交易版本套用；純結構升級不改原交易。
do $$ begin
  if md5(pg_get_functiondef('public.consume_session(uuid,date,uuid,text,boolean,date)'::regprocedure))<>'6b6e24696e508288d5a24fca3212c8c9' then raise exception '原交易函式已改變：consume_session，停止升級'; end if;
  if md5(pg_get_functiondef('public.create_purchase_with_first_payment(jsonb,jsonb)'::regprocedure))<>'d74801f371d2331462bc8b341cb2050f' then raise exception '原交易函式已改變：create_purchase_with_first_payment，停止升級'; end if;
  if md5(pg_get_functiondef('public.finance_net_v1(numeric)'::regprocedure))<>'1966efc07e06a179ac05109aefa15d6c' then raise exception '原交易函式已改變：finance_net_v1，停止升級'; end if;
  if md5(pg_get_functiondef('public.finance_session_net_v1(numeric,integer,integer)'::regprocedure))<>'5bb1dbbae6f152765c419b7b96af8721' then raise exception '原交易函式已改變：finance_session_net_v1，停止升級'; end if;
end $$;
create schema operation_private;
revoke all on schema operation_private from public,anon,authenticated,service_role;
grant usage on schema operation_private to authenticated;
create table operation_private.requests (
  actor_id uuid not null,
  operation_id uuid not null,
  operation_kind text not null check(operation_kind in ('purchase','usage')),
  state text not null check(state in ('completed','cancelled')),
  request_payload jsonb,
  response_payload jsonb,
  created_at timestamptz not null default clock_timestamp(),
  primary key(actor_id,operation_id),
  check ((state='completed' and request_payload is not null and response_payload is not null)
    or (state='cancelled' and request_payload is null and response_payload is null))
);
alter table operation_private.requests enable row level security;
revoke all on operation_private.requests from public,anon,authenticated,service_role;
comment on table operation_private.requests is 'v1.13.19 持久化操作收據與取消墓碑；不得刪除後重用識別碼；非財務原始交易。';

create function operation_private.actor() returns uuid language plpgsql
security definer set search_path='' as $$
declare actor_id uuid:=auth.uid();
begin
  if actor_id is null or not exists(select 1 from public.profiles p where p.id=actor_id and p.active
      and p.role in ('coach','shared_coach','manager','admin')) then
    raise exception using errcode='42501',message='未登入或帳號已停用，不能處理操作識別碼';
  end if;
  return actor_id;
end $$;
-- 私有內部 helper 不授予一般使用者執行。
revoke all on function operation_private.actor() from public,anon,authenticated,service_role;

create function operation_private.control(p_operation_id uuid,p_kind text,p_cancel boolean default false)
returns jsonb language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=operation_private.actor(); r operation_private.requests%rowtype;
begin
  if p_operation_id is null or p_kind not in ('purchase','usage') or p_kind is null then
    raise exception '操作識別碼及類型不可空白';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(a::text||':'||p_operation_id::text,0));
  perform operation_private.actor();
  select * into r from operation_private.requests where actor_id=a and operation_id=p_operation_id;
  if found then
    if r.operation_kind<>p_kind then raise exception '同一操作識別碼不可改變操作類型'; end if;
    return pg_catalog.jsonb_build_object('state',r.state,'result',r.response_payload);
  end if;
  if p_cancel then
    insert into operation_private.requests(actor_id,operation_id,operation_kind,state)
    values(a,p_operation_id,p_kind,'cancelled');
    return '{"state":"cancelled"}'::jsonb;
  end if;
  return '{"state":"not_found"}'::jsonb;
end $$;
revoke all on function operation_private.control(uuid,text,boolean) from public,anon,authenticated,service_role;
grant execute on function operation_private.control(uuid,text,boolean) to authenticated;

create function operation_private.purchase(p_operation_id uuid,p_purchase jsonb,p_first_payment jsonb)
returns jsonb language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=operation_private.actor(); r operation_private.requests%rowtype; result jsonb;
  payload jsonb:=pg_catalog.jsonb_build_object('p_purchase',p_purchase,'p_first_payment',p_first_payment);
begin
  if p_operation_id is null then raise exception '購課須提供操作識別碼'; end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(a::text||':'||p_operation_id::text,0));
  perform operation_private.actor();
  select * into r from operation_private.requests where actor_id=a and operation_id=p_operation_id;
  if found then
    if r.operation_kind<>'purchase' then raise exception '同一操作識別碼不可改變操作類型'; end if;
    if r.state='cancelled' then raise exception '本次操作已取消，禁止延遲請求重新建立購課'; end if;
    if r.request_payload is distinct from payload then
      raise exception '操作識別碼已使用，但購課內容不同；請先查核原結果，再開始新一筆';
    end if;
    return r.response_payload;
  end if;
  -- 既有函式自行驗證 active、角色、教練歸屬、日期、課程、金額及 JSON 禁用欄位。
  -- 此 wrapper 因私有收據需要 DEFINER；不可刪除既有函式內的業務授權檢查。
  result:=public.create_purchase_with_first_payment(p_purchase,p_first_payment);
  if result->>'purchase_id' is null or result->>'payment_id' is null then
    raise exception '購課或首期付款未取得完整確認，整次操作回滾';
  end if;
  insert into operation_private.requests(actor_id,operation_id,operation_kind,state,request_payload,response_payload)
  values(a,p_operation_id,'purchase','completed',payload,result);
  return result;
end $$;
revoke all on function operation_private.purchase(uuid,jsonb,jsonb) from public,anon,authenticated,service_role;
grant execute on function operation_private.purchase(uuid,jsonb,jsonb) to authenticated;

create function operation_private.usage(p_operation_id uuid,p_purchase_id uuid,p_usage_date date,
  p_coach_id uuid,p_note text default null,p_is_makeup boolean default false,p_actual_usage_date date default null)
returns jsonb language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=operation_private.actor(); actor_role text; r operation_private.requests%rowtype;
  p public.purchases%rowtype; u public.session_usages%rowtype; result jsonb;
  payload jsonb:=pg_catalog.jsonb_build_object('p_purchase_id',p_purchase_id,'p_usage_date',p_usage_date,
    'p_coach_id',p_coach_id,'p_note',nullif(pg_catalog.btrim(p_note),''),
    'p_is_makeup',coalesce(p_is_makeup,false),'p_actual_usage_date',coalesce(p_actual_usage_date,p_usage_date));
begin
  if p_operation_id is null or p_purchase_id is null or p_usage_date is null or p_coach_id is null then
    raise exception '銷課操作識別碼、購課、日期及教練不可空白';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(a::text||':'||p_operation_id::text,0));
  perform operation_private.actor();
  select role::text into actor_role from public.profiles where id=a and active;
  select * into r from operation_private.requests where actor_id=a and operation_id=p_operation_id;
  if found then
    if r.operation_kind<>'usage' then raise exception '同一操作識別碼不可改變操作類型'; end if;
    if r.state='cancelled' then raise exception '本次操作已取消，禁止延遲請求重新扣課'; end if;
    if r.request_payload is distinct from payload then
      raise exception '操作識別碼已使用，但銷課內容不同；請先查核原結果，再開始新一筆';
    end if;
    return r.response_payload;
  end if;
  -- 明確重建原本 INVOKER 的購課可讀範圍與使用紀錄可寫範圍，不能由 DEFINER 放寬。
  select * into p from public.purchases where id=p_purchase_id for update;
  if not found or (actor_role='coach' and (p.coach_id<>a or p_coach_id<>a)) then
    raise exception using errcode='42501',message='無權替此購課或教練建立銷課';
  end if;
  if not exists(select 1 from public.profiles where id=p_coach_id and active and role='coach') then
    raise exception '授課教練不是有效教練';
  end if;
  if actor_role='coach' and p_usage_date<(current_timestamp at time zone 'Asia/Taipei')::date then
    raise exception using errcode='42501',message='教練只能登錄今天或未來的銷課日期';
  end if;
  if not pg_catalog.isfinite(p_usage_date) or not pg_catalog.isfinite(coalesce(p_actual_usage_date,p_usage_date)) then
    raise exception '銷課日期必須是有效日期';
  end if;
  -- 補單資格、課程狀態、剩餘堂數、金額尾差與每日時數仍交原 consume_session 檢查。
  u:=public.consume_session(p_purchase_id,p_usage_date,p_coach_id,p_note,p_is_makeup,p_actual_usage_date);
  result:=pg_catalog.to_jsonb(u);
  insert into operation_private.requests(actor_id,operation_id,operation_kind,state,request_payload,response_payload)
  values(a,p_operation_id,'usage','completed',payload,result);
  return result;
end $$;
revoke all on function operation_private.usage(uuid,uuid,date,uuid,text,boolean,date) from public,anon,authenticated,service_role;
grant execute on function operation_private.usage(uuid,uuid,date,uuid,text,boolean,date) to authenticated;

create function public.create_purchase_idempotent(p_operation_id uuid,p_purchase jsonb,p_first_payment jsonb)
returns jsonb language sql security invoker set search_path='' as $$
  select operation_private.purchase(p_operation_id,p_purchase,p_first_payment);
$$;
create function public.consume_session_idempotent(p_operation_id uuid,p_purchase_id uuid,p_usage_date date,
  p_coach_id uuid,p_note text default null,p_is_makeup boolean default false,p_actual_usage_date date default null)
returns jsonb language sql security invoker set search_path='' as $$
  select operation_private.usage(p_operation_id,p_purchase_id,p_usage_date,p_coach_id,p_note,p_is_makeup,p_actual_usage_date);
$$;
create function public.operation_status(p_operation_id uuid,p_kind text)
returns jsonb language sql security invoker set search_path='' as $$
  select operation_private.control(p_operation_id,p_kind,false);
$$;
create function public.cancel_operation(p_operation_id uuid,p_kind text)
returns jsonb language sql security invoker set search_path='' as $$
  select operation_private.control(p_operation_id,p_kind,true);
$$;
revoke all on function public.create_purchase_idempotent(uuid,jsonb,jsonb) from public,anon,authenticated,service_role;
revoke all on function public.consume_session_idempotent(uuid,uuid,date,uuid,text,boolean,date) from public,anon,authenticated,service_role;
revoke all on function public.operation_status(uuid,text) from public,anon,authenticated,service_role;
revoke all on function public.cancel_operation(uuid,text) from public,anon,authenticated,service_role;
grant execute on function public.create_purchase_idempotent(uuid,jsonb,jsonb) to authenticated;
grant execute on function public.consume_session_idempotent(uuid,uuid,date,uuid,text,boolean,date) to authenticated;
grant execute on function public.operation_status(uuid,text) to authenticated;
grant execute on function public.cancel_operation(uuid,text) to authenticated;
notify pgrst,'reload schema';
