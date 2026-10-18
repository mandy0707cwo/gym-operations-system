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

CREATE OR REPLACE FUNCTION public.create_purchase_with_first_payment(p_purchase jsonb, p_first_payment jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_actor uuid := auth.uid();
  v_role text;
  v_member_id uuid;
  v_coach_id uuid;
  v_course_name text;
  v_kind public.purchase_kind;
  v_plan public.payment_plan;
  v_sessions integer;
  v_hours numeric(4,2);
  v_total numeric(12,2);
  v_count smallint;
  v_purchase_date date;
  v_expiry_date date;
  v_paid numeric(12,2);
  v_paid_date date;
  v_catalog public.course_catalog%rowtype;
  v_purchase_id uuid;
  v_payment_id uuid;
begin
  if v_actor is null then
    raise exception using errcode='42501', message='請先登入後再建立購課與首期付款';
  end if;
  select p.role::text into v_role from public.profiles p
    where p.id=v_actor and p.active;
  if v_role is null or v_role not in ('coach','shared_coach','manager','admin') then
    raise exception using errcode='42501', message='帳號未啟用或沒有購課權限';
  end if;
  if p_purchase is null or pg_catalog.jsonb_typeof(p_purchase)<>'object'
     or p_first_payment is null or pg_catalog.jsonb_typeof(p_first_payment)<>'object' then
    raise exception '購課與首期付款資料格式不正確';
  end if;
  -- 不允許呼叫者指定資料庫 ID、建立者、狀態或首期期次。
  if p_purchase ?| array['id','created_by','created_at','status']
     or p_first_payment ?| array['id','purchase_id','created_by','created_at','installment_no','payment_kind'] then
    raise exception using errcode='42501', message='不能自行指定交易識別碼、建立者或首期期次';
  end if;
  v_member_id := (p_purchase->>'member_id')::uuid;
  v_coach_id := (p_purchase->>'coach_id')::uuid;
  v_course_name := pg_catalog.btrim(p_purchase->>'course_name');
  v_kind := (p_purchase->>'purchase_kind')::public.purchase_kind;
  v_plan := (p_purchase->>'payment_plan')::public.payment_plan;
  v_sessions := (p_purchase->>'total_sessions')::integer;
  v_hours := (p_purchase->>'session_hours')::numeric;
  v_total := (p_purchase->>'total_amount')::numeric;
  v_count := (p_purchase->>'installment_count')::smallint;
  v_purchase_date := (p_purchase->>'purchase_date')::date;
  v_expiry_date := (p_purchase->>'expiry_date')::date;
  v_paid := (p_first_payment->>'amount')::numeric;
  v_paid_date := (p_first_payment->>'paid_date')::date;
  if v_member_id is null or v_coach_id is null or v_kind is null or v_plan is null
     or nullif(v_course_name,'') is null or v_sessions is null or v_sessions<=0
     or v_hours is null or v_hours<=0 or v_hours in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
     or v_total is null or v_total<=0 or v_total in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
     or v_paid is null or v_paid<=0 or v_paid in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
     or v_purchase_date is null or v_expiry_date is null or v_paid_date is null
     or not pg_catalog.isfinite(v_purchase_date) or not pg_catalog.isfinite(v_expiry_date)
     or not pg_catalog.isfinite(v_paid_date) then
    raise exception '必要欄位不可空白，堂數、時數及金額必須是有效正數';
  end if;
  if v_expiry_date<v_purchase_date then raise exception '有效日期不可早於購買日期'; end if;
  if v_paid>v_total then raise exception '此次支付金額不可大於成交總金額'; end if;
  if v_count is null or (v_plan='full' and (v_count<>1 or v_paid<>v_total))
     or (v_plan='installment' and v_count not in (2,3)) then
    raise exception '未分期須一次付清，分期總期數須為 2 或 3';
  end if;
  if v_role='coach' and (v_coach_id<>v_actor
     or v_purchase_date<(current_timestamp at time zone 'Asia/Taipei')::date
     or v_paid_date<(current_timestamp at time zone 'Asia/Taipei')::date) then
    raise exception using errcode='42501', message='教練僅可建立自己的購課及今日或未來的付款';
  end if;
  if not exists(select 1 from public.members m where m.id=v_member_id and m.active) then
    raise exception '客戶不存在、未啟用或無權存取';
  end if;
  if not exists(select 1 from public.profiles p where p.id=v_coach_id and p.active and p.role='coach') then
    raise exception '指導教練不存在或未啟用';
  end if;
  select * into v_catalog from public.course_catalog c where c.course_name=v_course_name and c.active;
  if not found then raise exception '課程不存在或已停用'; end if;
  if v_hours<>v_catalog.session_hours then raise exception '每堂課時數與課程設定不同，請重新選擇課程'; end if;
  -- 報表分類取課程管理資料，不接受任意偽造分類。
  if coalesce(nullif(pg_catalog.btrim(p_purchase->>'report_category'),''),'未分類')
     <>coalesce(nullif(pg_catalog.btrim(v_catalog.report_category),''),'未分類') then
    raise exception '報表分類已異動，請重新選擇課程';
  end if;

  insert into public.purchases(
    member_id,purchase_kind,coach_id,course_name,report_category,total_sessions,session_hours,
    total_amount,purchase_date,expiry_date,payment_plan,installment_count,referral,note,created_by
  ) values(
    v_member_id,v_kind,v_coach_id,v_course_name,
    coalesce(nullif(pg_catalog.btrim(v_catalog.report_category),''),'未分類'),v_sessions,v_hours,
    v_total,v_purchase_date,v_expiry_date,v_plan,v_count,
    nullif(pg_catalog.btrim(p_purchase->>'referral'),''),nullif(pg_catalog.btrim(p_purchase->>'note'),''),v_actor
  ) returning id into v_purchase_id;

  insert into public.purchase_payments(purchase_id,installment_no,amount,paid_date,payment_kind,created_by)
  values(v_purchase_id,1,v_paid,v_paid_date,'installment',v_actor)
  returning id into v_payment_id;

  -- 不吞例外、不提交部分資料；任一步驟拒絕，整次 RPC 交易由 PostgreSQL 回滾。
  return pg_catalog.jsonb_build_object('id',v_purchase_id,'purchase_id',v_purchase_id,'payment_id',v_payment_id);
end;
$function$;

CREATE OR REPLACE FUNCTION public.finance_net_v1(gross numeric)
 RETURNS numeric
 LANGUAGE plpgsql
 IMMUTABLE STRICT
 SET search_path TO ''
AS $function$
begin
  if gross in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) then
    raise exception '金額須為有限數值';
  end if;
  return round(gross/1.05,0);
end $function$;

CREATE OR REPLACE FUNCTION public.finance_session_net_v1(gross numeric, sessions integer, seq integer)
 RETURNS numeric
 LANGUAGE plpgsql
 IMMUTABLE STRICT
 SET search_path TO ''
AS $function$
declare unit_net numeric; final_net numeric;
begin
  if gross < 0 or sessions <= 0 or seq <= 0 or seq > sessions then
    raise exception '成交金額、購課堂數或銷課堂次無效';
  end if;
  unit_net := public.finance_net_v1(gross/sessions);
  final_net := public.finance_net_v1(gross)-unit_net*(sessions-1);
  if final_net < 0 then raise exception '未稅尾差為負，請先查核課程金額及堂數'; end if;
  return case when seq=sessions then final_net else unit_net end;
end $function$;

