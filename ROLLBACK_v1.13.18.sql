-- v1.13.18 資料回復候選；必須先還原 v1.13.14 程式，再由管理員在顯式交易中執行。
-- 本程序不是完整資料庫還原。任何新交易或列異動即停止，保留全部稽核與備份。
set local lock_timeout='5s';
set local statement_timeout='45s';
lock table public.purchases,public.purchase_payments,public.session_usages,public.trial_items,
public.single_sales,public.project_entries,public.project_deposits,public.course_terminations,
public.project_wallet_transactions,public.project_receipt_transactions in share row exclusive mode;
do $$ declare tbl text; mismatch bigint; begin
 for tbl in select distinct table_name from finance_private.before_rows where batch='v1.13.18' loop
 execute format('select count(*) from public.%I t full join
 (select row_id,new_row from finance_private.change_log where table_name=$1 and action=''HISTORICAL_ALIGNMENT'') e
 on t.id=e.row_id where t.id is null or e.row_id is null or to_jsonb(t) is distinct from e.new_row',tbl)
 into mismatch using tbl;
 if mismatch<>0 then raise exception '資料表 % 有後續新增或修改，禁止覆蓋，須另做回復計畫',tbl; end if;
 end loop;
end $$;
drop trigger finance_rebuild on public.purchases;
drop trigger finance_rebuild on public.purchase_payments;
drop trigger finance_rebuild on public.session_usages;
drop trigger finance_rebuild on public.course_terminations;
update public.session_usages u set deducted_net_amount=(b.original->>'deducted_net_amount')::numeric,
calculation_rule_version='restored-pre-v1.13.18'
from finance_private.before_rows b where b.batch='v1.13.18' and b.table_name='session_usages' and b.row_id=u.id;
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
  v_remaining_amount := greatest(round(v_purchase.total_amount-v_used_amount,2),0);
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
    v_deducted_net := round(v_purchase.total_amount/1.05,0)-v_prior_net;
  else
    v_deducted_net := round((v_purchase.total_amount/v_purchase.total_sessions)/1.05,0);
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
insert into finance_private.change_log(table_name,row_id,action,old_row,new_row,actor,session_actor,rule_version)
values('finance_release','00000000-0000-0000-0000-000000000018','REVERT_BATCH',
'{"version":"v1.13.18"}','{"version":"v1.13.14","derived_columns_retained":true}',auth.uid(),session_user,'restored-pre-v1.13.18');
do $$ begin
 if exists(select 1 from public.session_usages u join finance_private.before_rows b on b.table_name='session_usages'
 and b.row_id=u.id and b.batch='v1.13.18' where u.deducted_net_amount<>(b.original->>'deducted_net_amount')::numeric) then
 raise exception '銷課未稅回復不符原值'; end if;
end $$;
notify pgrst,'reload schema';

