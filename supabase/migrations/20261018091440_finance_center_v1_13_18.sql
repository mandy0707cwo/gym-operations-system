-- 執行前完整來源比對；來源有任何更新即停止，不覆蓋新交易。
set local lock_timeout = '5s';
set local statement_timeout = '45s';
lock table public.purchases,public.purchase_payments,public.session_usages,public.trial_items,
 public.single_sales,public.project_entries,public.project_deposits,public.course_terminations in share row exclusive mode;
do $$ declare tbl text; expected text; actual text; begin
 for tbl,expected in select * from (values
 ('purchases','9dba65317f219bdbc0a53f5b7e618852'),
 ('purchase_payments','52c342d20888ad8b5d9b06ef4096d34d'),
 ('session_usages','76c43f7a5d52c8a53cb91f5dd63c27e3'),
 ('trial_items','8d4f6239c7f86427f54d4106d52a545c'),
 ('single_sales','96023b29fba30c5a264ae479e68118ca'),
 ('project_entries','b7f5af9a45054be83ec4cc531f1d10a6'),
 ('project_deposits','b19119c8da26ee464943a7df6305a0de'),
 ('course_terminations','3437b83810e5721489eb7fc447448b92')) v(t,h) loop
 execute format('select md5(string_agg(to_jsonb(t)::text,''|'' order by id)) from public.%I t',tbl) into actual;
 if actual is distinct from expected then raise exception '來源 % 已改變，停止升級，需重新備份及核對',tbl; end if;
 end loop;
end $$;
-- v1.13.18：唯一未稅規格、保存值、更正稽核。由版本化 migration 套用。
-- 只新增派生欄位及調整銷課未稅，不改歷史含稅現金、日期、ID、時數或堂次。
set local lock_timeout = '5s';
set local statement_timeout = '45s';
create schema if not exists finance_private;
revoke all on schema finance_private from public, anon, authenticated;

create table finance_private.batches (
  version text primary key, approved_by_user text not null, approved_on date not null,
  backup_sha256 text not null, restore_test_passed boolean not null,
  restore_test_deferred_by_user boolean not null, created_at timestamptz not null default now()
);
alter table finance_private.batches enable row level security;
insert into finance_private.batches values ('v1.13.18',
  '使用者：已經完成備份。請依循新規則，全面修正線上系統。',date '2026-10-18',
  '703391bb8586852dd0421b9331aa0aa5462c37d3911b4a33961a333f7ff40167',false,true,now());

create table finance_private.before_rows (
  batch text not null, table_name text not null, row_id uuid not null,
  original jsonb not null, captured_at timestamptz not null default clock_timestamp(),
  primary key(batch, table_name, row_id)
);
create table finance_private.change_log (
  id bigint generated always as identity primary key, table_name text not null,
  row_id uuid not null, action text not null, old_row jsonb, new_row jsonb,
  actor uuid, actor_basis text not null default 'database_session', session_actor text not null, rule_version text not null,
  txid bigint not null default txid_current(), changed_at timestamptz not null default clock_timestamp()
);
alter table finance_private.before_rows enable row level security;
alter table finance_private.change_log enable row level security;
revoke all on all tables in schema finance_private from public, anon, authenticated;

create function public.finance_net_v1(gross numeric) returns numeric
language plpgsql immutable strict security invoker set search_path = '' as $$
begin
  if gross in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) then
    raise exception '金額須為有限數值';
  end if;
  return round(gross/1.05,0);
end $$;
revoke all on function public.finance_net_v1(numeric) from public, anon;
grant execute on function public.finance_net_v1(numeric) to authenticated, service_role;

create function public.finance_session_net_v1(gross numeric, sessions integer, seq integer) returns numeric
language plpgsql immutable strict security invoker set search_path = '' as $$
declare unit_net numeric; final_net numeric;
begin
  if gross < 0 or sessions <= 0 or seq <= 0 or seq > sessions then
    raise exception '成交金額、購課堂數或銷課堂次無效';
  end if;
  unit_net := public.finance_net_v1(gross/sessions);
  final_net := public.finance_net_v1(gross)-unit_net*(sessions-1);
  if final_net < 0 then raise exception '未稅尾差為負，請先查核課程金額及堂數'; end if;
  return case when seq=sessions then final_net else unit_net end;
end $$;
revoke all on function public.finance_session_net_v1(numeric,integer,integer) from public, anon;
grant execute on function public.finance_session_net_v1(numeric,integer,integer) to authenticated, service_role;

-- 修改前的完整原列僅保存在非 API schema，不授權教練或匿名讀取。
do $$ declare tbl text; begin
  foreach tbl in array array['purchases','purchase_payments','session_usages','trial_items','single_sales',
    'project_entries','project_deposits','course_terminations','project_wallet_transactions','project_receipt_transactions'] loop
    execute format('insert into finance_private.before_rows(batch,table_name,row_id,original)
      select ''v1.13.18'',$1,t.id,to_jsonb(t) from public.%I t',tbl) using tbl;
  end loop;
end $$;

alter table public.purchases add column total_net_amount numeric(14,0)
  generated always as (public.finance_net_v1(total_amount)) stored;
do $$ declare tbl text; field text; begin
  for tbl,field in select * from (values ('trial_items','amount'),('single_sales','amount'),
    ('project_entries','line_amount'),('project_deposits','amount'),
    ('project_wallet_transactions','amount'),('project_receipt_transactions','amount')) v(t,f) loop
    execute format('alter table public.%I add column net_amount numeric(14,0)
      generated always as (public.finance_net_v1(%I)) stored',tbl,field);
    execute format('alter table public.%I add column calculation_rule_version text
      generated always as (''historical-alignment-v3''::text) stored',tbl);
  end loop;
end $$;
alter table public.purchases add column calculation_rule_version text
  generated always as ('historical-alignment-v3'::text) stored;
alter table public.purchase_payments add column net_amount numeric(14,0);
alter table public.purchase_payments add column calculation_rule_version text;
alter table public.session_usages add column calculation_rule_version text;
alter table public.course_terminations add column remaining_net_amount numeric(14,0);
alter table public.course_terminations add column recognized_net_amount numeric(14,0);
alter table public.course_terminations add column fee_net_amount numeric(14,0);
alter table public.course_terminations add column refund_net_amount numeric(14,0);
alter table public.course_terminations add column calculation_rule_version text;

-- 僅供原始列交易觸發器及 postgres 升級作業呼叫；不是可由 API 執行的 RPC。
-- SECURITY DEFINER 用途是維護同一購課的派生值及不可竄改稽核，不授予原始交易權限。
create function finance_private.rebuild_purchase(pid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare p public.purchases%rowtype; r record; paid numeric:=0; prior_net numeric:=0;
  allocated numeric; base numeric; fee numeric;
begin
  if auth.uid() is null and session_user not in ('postgres','supabase_admin')
      and coalesce(current_setting('role',true),'') <> 'service_role' then
    raise exception '未授權的財務派生值更新';
  end if;
  select * into p from public.purchases where id=pid for update;
  if not found then return; end if;
  if exists(select 1 from public.session_usages where purchase_id=pid and session_seq>p.total_sessions) then
    raise exception '購課堂數不可小於既有銷課堂次';
  end if;
  update public.session_usages u set
    deducted_net_amount=public.finance_session_net_v1(p.total_amount,p.total_sessions,u.session_seq),
    calculation_rule_version='historical-alignment-v3'
  where u.purchase_id=pid and (u.deducted_net_amount is distinct from
    public.finance_session_net_v1(p.total_amount,p.total_sessions,u.session_seq)
    or u.calculation_rule_version is distinct from 'historical-alignment-v3');
  for r in select * from public.purchase_payments where purchase_id=pid order by paid_date,created_at,id loop
    paid:=paid+r.amount;
    allocated:=public.finance_net_v1(r.amount);
    if paid>=p.total_amount and r.amount>0 then
      allocated:=public.finance_net_v1(p.total_amount)+public.finance_net_v1(paid-p.total_amount)-prior_net;
    end if;
    if allocated<0 then raise exception '收款未稅尾差為負，須先查核'; end if;
    update public.purchase_payments set net_amount=allocated,calculation_rule_version='historical-alignment-v3'
      where id=r.id and (net_amount is distinct from allocated or calculation_rule_version is distinct from 'historical-alignment-v3');
    prior_net:=prior_net+allocated;
  end loop;
  for r in select * from public.course_terminations where purchase_id=pid loop
    if exists(select 1 from public.session_usages where purchase_id=pid and usage_date>r.termination_date) then
      raise exception '中止後仍有銷課，須先查核，不自動隱藏';
    end if;
    select coalesce(sum(net_amount),0) into base from public.purchase_payments
      where purchase_id=pid and paid_date<=r.termination_date;
    select base-coalesce(sum(deducted_net_amount),0) into base from public.session_usages
      where purchase_id=pid and usage_date<=r.termination_date;
    fee:=case when r.termination_type='refund' then public.finance_net_v1(r.fee_amount) else 0 end;
    if base<0 or fee>base then raise exception '中止實收未稅餘額不足，不得以歸零掩蓋'; end if;
    update public.course_terminations set remaining_net_amount=base,
      recognized_net_amount=case when r.termination_type='expired' then base else fee end,
      fee_net_amount=fee,refund_net_amount=case when r.termination_type='refund' then base-fee else 0 end,
      calculation_rule_version='historical-alignment-v3'
    where id=r.id and (remaining_net_amount is distinct from base
      or fee_net_amount is distinct from fee
      or refund_net_amount is distinct from case when r.termination_type='refund' then base-fee else 0 end
      or recognized_net_amount is distinct from case when r.termination_type='expired' then base else fee end
      or calculation_rule_version is distinct from 'historical-alignment-v3');
  end loop;
end $$;

-- 初次更正同一交易完成；原始列先保存，未稅派生值才回填。
do $$ declare r record; begin
  for r in select id from public.purchases order by id loop
    perform finance_private.rebuild_purchase(r.id);
  end loop;
end $$;

create function finance_private.source_changed() returns trigger
language plpgsql security definer set search_path = '' as $$
declare pid uuid;
begin
  if auth.uid() is null and session_user not in ('postgres','supabase_admin')
      and coalesce(current_setting('role',true),'') <> 'service_role' then
    raise exception '未授權的財務維護';
  end if;
  -- 內部 UPDATE 派生欄位不能遞迴啟動整筆重算。
  if pg_trigger_depth()>1 then return null; end if;
  pid:=(case when tg_table_name='purchases' then coalesce(to_jsonb(new)->>'id',to_jsonb(old)->>'id')
    else coalesce(to_jsonb(new)->>'purchase_id',to_jsonb(old)->>'purchase_id') end)::uuid;
  if tg_op='UPDATE' and tg_table_name<>'purchases' and (to_jsonb(old)->>'purchase_id') is distinct from (to_jsonb(new)->>'purchase_id') then
    raise exception '不得移動既有交易至另一購課；請另留更正紀錄';
  end if;
  perform finance_private.rebuild_purchase(pid);
  return null;
end $$;

create function finance_private.audit_change() returns trigger
language plpgsql security definer set search_path = '' as $$
declare actor_id uuid:=auth.uid(); basis text:='verified_jwt'; claimed text;
begin
  if auth.uid() is null and session_user not in ('postgres','supabase_admin')
      and coalesce(current_setting('role',true),'') <> 'service_role' then
    raise exception '未授權的財務稽核寫入';
  end if;
  if tg_op='UPDATE' and to_jsonb(old)=to_jsonb(new) then return null; end if;
  if actor_id is null then
    basis:='database_session';
    if coalesce(current_setting('role',true),'')='service_role' then
      claimed:=(coalesce(nullif(current_setting('request.headers',true),''),'{}')::jsonb)->>'x-finance-actor-id';
      if claimed is not null then
        select p.id into actor_id from public.profiles p where p.id=claimed::uuid and p.active and p.role='admin';
        if actor_id is null then raise exception '伺服器提供的財務操作人員不是有效管理員'; end if;
        basis:='trusted_server_header';
      end if;
    end if;
  end if;
  insert into finance_private.change_log(table_name,row_id,action,old_row,new_row,actor,actor_basis,session_actor,rule_version)
  values(tg_table_name,case when tg_op='DELETE' then old.id else new.id end,tg_op,
    case when tg_op<>'INSERT' then to_jsonb(old) end,
    case when tg_op<>'DELETE' then to_jsonb(new) end,actor_id,basis,session_user,'historical-alignment-v3');
  return null;
end $$;

-- 明確記錄此次歷史更正的新舊值（包含新保存欄位），與未來交易稽核分開。
do $$ declare tbl text; begin
  foreach tbl in array array['purchases','purchase_payments','session_usages','trial_items','single_sales',
    'project_entries','project_deposits','course_terminations','project_wallet_transactions','project_receipt_transactions'] loop
    execute format('insert into finance_private.change_log(table_name,row_id,action,old_row,new_row,actor,session_actor,rule_version)
      select $1,t.id,''HISTORICAL_ALIGNMENT'',b.original,to_jsonb(t),auth.uid(),session_user,''historical-alignment-v3''
      from public.%I t join finance_private.before_rows b on b.table_name=$1 and b.row_id=t.id and b.batch=''v1.13.18''',tbl) using tbl;
    execute format('create trigger finance_audit after insert or update or delete on public.%I
      for each row execute function finance_private.audit_change()',tbl);
  end loop;
  foreach tbl in array array['purchases','purchase_payments','session_usages','course_terminations'] loop
    execute format('create trigger finance_rebuild after insert or update or delete on public.%I
      for each row execute function finance_private.source_changed()',tbl);
  end loop;
end $$;
revoke all on all functions in schema finance_private from public, anon, authenticated, service_role;
revoke all on all sequences in schema finance_private from public, anon, authenticated;

alter table public.purchase_payments alter column net_amount set not null;
alter table public.purchase_payments alter column calculation_rule_version set not null;
alter table public.session_usages alter column calculation_rule_version set not null;
alter table public.course_terminations alter column remaining_net_amount set not null;
alter table public.course_terminations alter column recognized_net_amount set not null;
alter table public.course_terminations alter column fee_net_amount set not null;
alter table public.course_terminations alter column refund_net_amount set not null;
alter table public.course_terminations alter column calculation_rule_version set not null;
-- 新 INSERT 在 AFTER 觸發器計算之前，先允許暫時值；同一交易會覆寫為正式值。
alter table public.purchase_payments alter column net_amount set default 0;
alter table public.purchase_payments alter column calculation_rule_version set default 'historical-alignment-v3';
alter table public.session_usages alter column calculation_rule_version set default 'historical-alignment-v3';
alter table public.course_terminations alter column remaining_net_amount set default 0;
alter table public.course_terminations alter column recognized_net_amount set default 0;
alter table public.course_terminations alter column fee_net_amount set default 0;
alter table public.course_terminations alter column refund_net_amount set default 0;
alter table public.course_terminations alter column calculation_rule_version set default 'historical-alignment-v3';

notify pgrst, 'reload schema';


CREATE OR REPLACE FUNCTION public.consume_session(p_purchase_id uuid, p_usage_date date, p_coach_id uuid, p_note text DEFAULT NULL::text, p_is_makeup boolean DEFAULT false, p_actual_usage_date date DEFAULT NULL::date)
 RETURNS session_usages
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
declare
  v_purchase public.purchases%rowtype;
  v_used integer;
  v_next_seq integer;
  v_deducted numeric(12,2);
  v_deducted_net numeric(12,2);
  v_prior_net numeric(12,2);
  v_actual_usage_date date;
  v_row public.session_usages%rowtype;
begin
  if (coalesce(p_is_makeup,false) or coalesce(p_actual_usage_date,p_usage_date) <> p_usage_date)
     and not public.is_admin() then
    raise exception '僅系統管理員可以建立補單或指定實際銷課日期';
  end if;

  v_actual_usage_date := coalesce(p_actual_usage_date,p_usage_date);
  if not coalesce(p_is_makeup,false) then
    v_actual_usage_date := p_usage_date;
  end if;
  if coalesce(p_is_makeup,false) and v_actual_usage_date > p_usage_date then
    raise exception '補單的實際銷課日期不可晚於銷課日期';
  end if;

  select * into v_purchase
  from public.purchases
  where id=p_purchase_id
  for update;
  if not found then raise exception '找不到購買紀錄'; end if;
  if v_purchase.status <> 'active' then raise exception '此課程不是有效狀態'; end if;

  select count(*) into v_used
  from public.session_usages
  where purchase_id=p_purchase_id;
  if v_used >= v_purchase.total_sessions then raise exception '剩餘堂數不足'; end if;

  select candidate.seq into v_next_seq
  from generate_series(1,v_purchase.total_sessions) as candidate(seq)
  where not exists (
    select 1
    from public.session_usages usage
    where usage.purchase_id=p_purchase_id
      and usage.session_seq=candidate.seq
  )
  order by candidate.seq
  limit 1;
  if v_next_seq is null then raise exception '找不到可用的銷課堂次'; end if;

  -- 含稅金額：一般堂次平均分攤，最後一堂扣除全部含稅餘額。
  if v_used + 1 = v_purchase.total_sessions then
    select round(v_purchase.total_amount-coalesce(sum(deducted_amount),0),2)
      into v_deducted
    from public.session_usages
    where purchase_id=p_purchase_id;
  else
    v_deducted := round(v_purchase.total_amount/v_purchase.total_sessions,2);
  end if;

  select coalesce(sum(deducted_net_amount),0)
    into v_prior_net
  from public.session_usages
  where purchase_id=p_purchase_id;

  -- 未稅金額：一般堂次固定四捨五入，最後一堂補足整筆課程未稅總額。
  if v_used + 1 = v_purchase.total_sessions then
    v_deducted_net := public.finance_net_v1(v_purchase.total_amount)-v_prior_net;
  else
    v_deducted_net := public.finance_session_net_v1(v_purchase.total_amount,v_purchase.total_sessions,v_next_seq);
  end if;

  if v_deducted_net < 0 then
    raise exception '未稅尾差計算異常，請檢查既有銷課入帳金額';
  end if;

  insert into public.session_usages(
    purchase_id,usage_date,actual_usage_date,is_makeup,coach_id,
    session_seq,deducted_amount,deducted_net_amount,note,created_by
  ) values (
    p_purchase_id,p_usage_date,v_actual_usage_date,coalesce(p_is_makeup,false),p_coach_id,
    v_next_seq,v_deducted,v_deducted_net,nullif(trim(p_note),''),auth.uid()
  ) returning * into v_row;

  insert into public.daily_operations(operation_date,coach_id,classes_held,classes_cancelled,trial_visits,trial_conversions)
  values(p_usage_date,p_coach_id,1,0,0,0)
  on conflict(operation_date,coach_id) do update
  set classes_held=(
    select count(*)
    from public.session_usages
    where usage_date=p_usage_date
      and coach_id=p_coach_id
  );

  if v_used+1=v_purchase.total_sessions then
    update public.purchases set status='completed' where id=p_purchase_id;
  end if;
  return v_row;
end; $function$;

CREATE OR REPLACE FUNCTION public.terminate_course(p_purchase_id uuid, p_termination_date date, p_termination_type text, p_charge_fee boolean DEFAULT false, p_completion_bonus_eligible boolean DEFAULT false, p_completion_bonus_coach_id uuid DEFAULT NULL::uuid, p_reason text DEFAULT NULL::text, p_note text DEFAULT NULL::text)
 RETURNS course_terminations
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
declare
  v_purchase public.purchases%rowtype;
  v_used_sessions integer;
  v_used_amount numeric(12,2);
  v_remaining_sessions integer;
  v_remaining_amount numeric(12,2);
  v_fee_rate numeric(6,5);
  v_fee_amount numeric(12,2);
  v_refund_amount numeric(12,2);
  v_recognized_amount numeric(12,2);
  v_row public.course_terminations%rowtype;
begin
  if not (select public.is_admin()) then
    raise exception '僅限系統管理員執行課程中止';
  end if;
  if p_termination_type not in ('expired','refund') then
    raise exception '中止類型必須為逾期或退費';
  end if;

  select * into v_purchase from public.purchases
  where id=p_purchase_id for update;
  if not found then raise exception '找不到購買紀錄'; end if;
  if v_purchase.status <> 'active' then raise exception '此課程不是有效狀態'; end if;
  if exists(select 1 from public.course_terminations where purchase_id=p_purchase_id) then
    raise exception '此課程已有中止紀錄';
  end if;

  select count(*)::integer, coalesce(sum(deducted_amount),0)
  into v_used_sessions, v_used_amount
  from public.session_usages where purchase_id=p_purchase_id;

  v_remaining_sessions := greatest(v_purchase.total_sessions-v_used_sessions,0);
  if p_termination_date is null or p_termination_date<v_purchase.purchase_date then
    raise exception '中止日期不可早於成交日期';
  end if;
  if exists(select 1 from public.session_usages where purchase_id=p_purchase_id and usage_date>p_termination_date)
    or exists(select 1 from public.purchase_payments where purchase_id=p_purchase_id and paid_date>p_termination_date) then
    raise exception '中止日期後仍有銷課或收款，請先核對日期，不得忽略後續交易';
  end if;
  select coalesce(sum(amount),0)-v_used_amount into v_remaining_amount
    from public.purchase_payments where purchase_id=p_purchase_id and paid_date<=p_termination_date;
  if v_remaining_amount<=0 then raise exception '實收款扣除銷課後無正數餘額，請先查核未繳款項'; end if;
  if v_remaining_sessions=0 then raise exception '此課程已完成，無法中止'; end if;

  if p_termination_type='refund' then
    v_fee_rate := case when p_charge_fee then 0.20 else 0 end;
    v_fee_amount := round(v_remaining_amount*v_fee_rate,2);
    v_refund_amount := greatest(v_remaining_amount-v_fee_amount,0);
    v_recognized_amount := v_fee_amount;
    p_completion_bonus_eligible := false;
    p_completion_bonus_coach_id := null;
  else
    v_fee_rate := 0;
    v_fee_amount := 0;
    v_refund_amount := 0;
    v_recognized_amount := v_remaining_amount;
    if p_completion_bonus_eligible and p_completion_bonus_coach_id is null then
      raise exception '計算結單獎金時必須指定歸屬教練';
    end if;
    if not p_completion_bonus_eligible then p_completion_bonus_coach_id := null; end if;
  end if;

  insert into public.course_terminations(
    purchase_id,termination_date,termination_type,remaining_sessions,remaining_amount,
    charge_fee,fee_rate,fee_amount,refund_amount,recognized_amount,
    completion_bonus_eligible,completion_bonus_coach_id,reason,note,created_by
  ) values (
    p_purchase_id,p_termination_date,p_termination_type,v_remaining_sessions,v_remaining_amount,
    p_termination_type='refund' and p_charge_fee,v_fee_rate,v_fee_amount,v_refund_amount,v_recognized_amount,
    p_termination_type='expired' and p_completion_bonus_eligible,p_completion_bonus_coach_id,
    nullif(trim(p_reason),''),nullif(trim(p_note),''),auth.uid()
  ) returning * into v_row;

  update public.purchases
  set status=case when p_termination_type='expired' then 'expired' else 'cancelled' end
  where id=p_purchase_id;

  return v_row;
end; $function$;


-- 所有原始業務欄位及筆數必須完全相同；唯一允許改動的原欄位是銷課未稅。
do $$ declare tbl text; mismatch bigint; additions text[]:=array['net_amount','total_net_amount',
 'calculation_rule_version','remaining_net_amount','recognized_net_amount','fee_net_amount','refund_net_amount']; begin
 foreach tbl in array array['purchases','purchase_payments','session_usages','trial_items','single_sales',
 'project_entries','project_deposits','course_terminations','project_wallet_transactions','project_receipt_transactions'] loop
 execute format('select count(*) from public.%I t full join
 (select * from finance_private.before_rows where table_name=$1 and batch=''v1.13.18'') b on b.row_id=t.id
 where t.id is null or b.row_id is null or
 ((to_jsonb(t)-$2)-case when $1=''session_usages'' then ''deducted_net_amount'' else ''__unused__'' end)
 is distinct from (b.original-case when $1=''session_usages'' then ''deducted_net_amount'' else ''__unused__'' end)',tbl)
 into mismatch using tbl,additions;
 if mismatch<>0 then raise exception '原始欄位變動 %：% 筆；整次升級回復',tbl,mismatch; end if;
 end loop;
 if exists(select 1 from public.session_usages u join public.purchases p on p.id=u.purchase_id
   where u.deducted_net_amount<>public.finance_session_net_v1(p.total_amount,p.total_sessions,u.session_seq)) then
   raise exception '銷課明細未符合共同規格'; end if;
end $$;

