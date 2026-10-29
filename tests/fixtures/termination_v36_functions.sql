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

CREATE OR REPLACE FUNCTION finance_private.source_changed()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$;

CREATE OR REPLACE FUNCTION finance_private.rebuild_purchase(pid uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$;
