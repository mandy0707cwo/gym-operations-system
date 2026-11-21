-- v1.13.49 本機候選：只新增工時及受控彙總，不改交易或排班。
begin;
create schema performance_private;
revoke all on schema performance_private from public,anon,authenticated;
grant usage on schema performance_private to authenticated;

create table performance_private.monthly_hours (
  month date not null check (isfinite(month) and extract(day from month)=1),
  coach_id uuid not null references public.profiles(id),
  minutes integer not null check (minutes>=0 and minutes<=44640),
  revision integer not null check (revision>0),
  updated_by uuid not null references public.profiles(id),
  updated_at timestamptz not null default clock_timestamp(),
  primary key(month,coach_id),
  check (minutes <= extract(day from (month+interval '1 month' - interval '1 day'))::int*1440)
);
create table performance_private.hours_receipts (
  actor uuid not null references public.profiles(id), operation_id uuid not null,
  payload jsonb not null, result jsonb not null, created_at timestamptz not null default clock_timestamp(),
  primary key(actor,operation_id)
);
create table performance_private.hours_audit (
  id bigint generated always as identity primary key,
  actor uuid not null references public.profiles(id), operation_id uuid not null,
  month date not null, coach_id uuid not null references public.profiles(id),
  before_row jsonb, after_row jsonb not null, created_at timestamptz not null default clock_timestamp()
);
alter table performance_private.monthly_hours enable row level security;
alter table performance_private.hours_receipts enable row level security;
alter table performance_private.hours_audit enable row level security;
revoke all on all tables in schema performance_private from public,anon,authenticated;
revoke all on all sequences in schema performance_private from public,anon,authenticated;

create function performance_private.actor() returns uuid language plpgsql stable security definer set search_path='' as $$
begin
  if auth.uid() is null or not exists(select 1 from public.profiles where id=auth.uid() and active and role in ('manager','admin')) then
    raise exception '績效功能僅限有效主管與系統管理員' using errcode='42501';
  end if;
  return auth.uid();
end $$;

-- 不以目前帳號啟用狀態排除歷史業績，也不公開會員清單。
create function performance_private.roster() returns jsonb language sql stable security definer set search_path='' as $$
  select coalesce(jsonb_agg(jsonb_build_object('id',p.id,'username',p.username,'display_name',p.display_name,'active',p.active)
    order by p.username nulls last,p.id),'[]'::jsonb)
  from public.profiles p where performance_private.actor() is not null and
    (p.role='coach' or exists(select 1 from public.purchases where coach_id=p.id)
     or exists(select 1 from public.session_usages where coach_id=p.id)
     or exists(select 1 from public.trial_items where coach_id=p.id)
     or exists(select 1 from public.single_sales where coach_id=p.id)
     or exists(select 1 from public.project_entries where coach_id=p.id)
     or exists(select 1 from public.session_cancellations where coach_id=p.id)
     or exists(select 1 from public.course_termination_events where purchase_snapshot->>'coach_id'=p.id::text)
     or exists(select 1 from performance_private.monthly_hours where coach_id=p.id));
$$;

create function performance_private.work_hours(p_month date) returns jsonb language plpgsql stable security definer set search_path='' as $$
begin
  perform performance_private.actor();
  if p_month is null or not isfinite(p_month) or extract(day from p_month)<>1 then raise exception '請選擇工時月份'; end if;
  return jsonb_build_object('month',p_month,'coaches',performance_private.roster(),
    'hours',coalesce((select jsonb_agg(to_jsonb(h)||jsonb_build_object('updated_by_name',p.display_name) order by h.coach_id)
      from performance_private.monthly_hours h join public.profiles p on p.id=h.updated_by where month=p_month),'[]'::jsonb));
end $$;

create function performance_private.save_hours(p_operation_id uuid,p_month date,p_rows jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare who uuid:=performance_private.actor(); payload jsonb; receipt performance_private.hours_receipts%rowtype;
  item jsonb; coach uuid; mins numeric; expected numeric; prior performance_private.monthly_hours%rowtype;
  saved performance_private.monthly_hours%rowtype; result jsonb;
begin
  if p_operation_id is null or p_month is null or not isfinite(p_month) or extract(day from p_month)<>1
     or jsonb_typeof(p_rows) is distinct from 'array' or jsonb_array_length(p_rows)=0 then raise exception '工時儲存資料不完整'; end if;
  payload:=jsonb_build_object('month',p_month,'rows',p_rows);
  -- 同操作重送與同月份修改序列化；所有列成功才提交。
  perform pg_advisory_xact_lock(hashtextextended(who::text||p_operation_id::text,49));
  select * into receipt from performance_private.hours_receipts where actor=who and operation_id=p_operation_id;
  if found then
    if receipt.payload<>payload then raise exception '操作識別碼相同但內容不同'; end if;
    return receipt.result;
  end if;
  perform pg_advisory_xact_lock(hashtextextended('performance-hours:'||p_month::text,49));
  if (select count(*)<>count(distinct x->>'coach_id') from jsonb_array_elements(p_rows) x) then raise exception '教練資料重複'; end if;
  for item in select value from jsonb_array_elements(p_rows) loop
    coach:=(item->>'coach_id')::uuid; mins:=(item->>'minutes')::numeric; expected:=(item->>'revision')::numeric;
    if coach is null or mins is null or expected is null or mins::text in ('NaN','Infinity','-Infinity')
       or expected::text in ('NaN','Infinity','-Infinity') or mins<>trunc(mins) or mins<0
       or mins>extract(day from(p_month+interval '1 month' - interval '1 day'))::int*1440
       or expected<>trunc(expected) or expected<0 or not exists(select 1 from public.profiles where id=coach) then
      raise exception '工時需為有效非負時數（最小單位1分鐘），且不得超過當月日曆總時數';
    end if;
    select * into prior from performance_private.monthly_hours where month=p_month and coach_id=coach for update;
    if coalesce(prior.revision,0)<>expected then raise exception '工時已由其他人修改，請重新載入' using errcode='40001'; end if;
    insert into performance_private.monthly_hours(month,coach_id,minutes,revision,updated_by)
      values(p_month,coach,mins::int,expected::int+1,who)
      on conflict(month,coach_id) do update set minutes=excluded.minutes,revision=excluded.revision,updated_by=who,updated_at=clock_timestamp()
      returning * into saved;
    insert into performance_private.hours_audit(actor,operation_id,month,coach_id,before_row,after_row)
      values(who,p_operation_id,p_month,coach,case when prior.coach_id is null then null else to_jsonb(prior) end,to_jsonb(saved));
  end loop;
  result:=performance_private.work_hours(p_month);
  insert into performance_private.hours_receipts(actor,operation_id,payload,result) values(who,p_operation_id,payload,result);
  return result;
end $$;

create function performance_private.report(p_start date,p_end date) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare facts jsonb; cohorts jsonb;
begin
  perform performance_private.actor();
  if p_start is null or p_end is null or not isfinite(p_start) or not isfinite(p_end)
     or p_start>p_end or p_start<'1901-01-01' or p_end>'9998-12-31' then raise exception '請提供有效的統計日期區間'; end if;
  -- 原存未稅先檢核，不能以缺值當0或另行除稅。
  if exists(select 1 from public.purchases where purchase_date between p_start and p_end and
      (total_net_amount is null or total_net_amount<>public.finance_net_v1(total_amount) or nullif(calculation_rule_version,'') is null))
    or exists(select 1 from public.session_usages where usage_date between p_start and p_end and
      (deducted_net_amount is null or deducted_net_amount<0 or deducted_net_amount<>trunc(deducted_net_amount) or nullif(calculation_rule_version,'') is null))
    or exists(select 1 from (
      select entry_date,amount,net_amount,calculation_rule_version from public.trial_items
      union all select entry_date,amount,net_amount,calculation_rule_version from public.single_sales
      union all select entry_date,line_amount,net_amount,calculation_rule_version from public.project_entries
    ) x where entry_date between p_start and p_end and (amount is null or net_amount is null or net_amount<>public.finance_net_v1(amount) or nullif(calculation_rule_version,'') is null))
    or exists(select 1 from public.project_entries where entry_date between p_start and p_end and (coach_id is null or item_hours is null or item_hours<=0))
    or exists(select 1 from public.course_termination_events where termination_date between p_start and p_end and termination_type='refund' and refund_net_amount is null)
    or exists(select 1 from public.session_usages u join public.purchases p on p.id=u.purchase_id where u.usage_date<=p_end group by p.id,p.total_sessions having count(*)>p.total_sessions)
  then raise exception '績效來源資料不完整或與正式計算中心不一致，請查核，未顯示部分合計'; end if;

  with finished as (
    select p.id,p.coach_id,max(u.usage_date) as day from public.purchases p join public.session_usages u on u.purchase_id=p.id
      where u.usage_date<=p_end group by p.id having count(*)=p.total_sessions
  ), sources as (
    select p.coach_id,p.purchase_date as day,jsonb_build_object('sales_net',p.total_net_amount,'sales_sessions',p.total_sessions,
      'first_orders',case when p.purchase_kind='first' then 1 else 0 end,'renewal_orders',case when p.purchase_kind='renewal' then 1 else 0 end) metrics
      from public.purchases p where p.purchase_date between p_start and p_end
    union all select u.coach_id,u.usage_date,jsonb_build_object('usage_net',u.deducted_net_amount,'usage_sessions',1,'usage_hours',p.session_hours)
      from public.session_usages u join public.purchases p on p.id=u.purchase_id where u.usage_date between p_start and p_end
    union all select coach_id,entry_date,jsonb_build_object('trial_visits',1,'paid_trial_visits',case when amount>0 then 1 else 0 end,'trial_hours',hours,'oneoff_net',net_amount)
      from public.trial_items where entry_date between p_start and p_end
    union all select coach_id,entry_date,jsonb_build_object('single_hours',hours,'oneoff_net',net_amount) from public.single_sales where entry_date between p_start and p_end
    union all select coach_id,entry_date,jsonb_build_object('project_hours',item_hours*quantity,'oneoff_net',net_amount) from public.project_entries where entry_date between p_start and p_end
    union all select coach_id,cancel_date,jsonb_build_object('cancelled_sessions',cancelled_sessions) from public.session_cancellations where cancel_date between p_start and p_end
    union all select c.coach_id,c.day,jsonb_build_object('completed_courses',1) from finished c where c.day between p_start and p_end
      and not exists(select 1 from public.course_terminations t where t.purchase_id=c.id and coalesce(t.correction_posted_on,t.termination_date)<=c.day
        and (t.reversed_at is null or (t.reversed_at at time zone 'Asia/Taipei')::date>c.day))
    union all select coalesce((t.purchase_snapshot->>'coach_id')::uuid,p.coach_id),t.termination_date,
      jsonb_build_object('refund_courses',case when t.is_reversal then -1 else 1 end,'refund_net',t.refund_net_amount)
      from public.course_termination_events t join public.purchases p on p.id=t.purchase_id
      where t.termination_type='refund' and t.termination_date between p_start and p_end
  ), grouped as (
    select coach_id,day,k.key metric,sum(k.value::numeric) value from sources cross join lateral jsonb_each_text(metrics) k group by coach_id,day,k.key
  ) select coalesce(jsonb_agg(to_jsonb(g) order by coach_id,day,metric),'[]'::jsonb) into facts from grouped g;

  -- 期初為開始日之前一日收盤，期末為截止日收盤；新會員不進期初群組。
  with periods as (
    select p_start start_date,p_end end_date
    union select greatest(d::date,p_start),least((d+interval '1 month' - interval '1 day')::date,p_end)
      from generate_series(date_trunc('month',p_start::timestamp),date_trunc('month',p_end::timestamp),interval '1 month') d
  ), boundaries as (
    select start_date,end_date,start_date-1 snapshot,'opening' side from periods
    union all select start_date,end_date,end_date,'closing' from periods
  ), valid_members as (
    select distinct b.start_date,b.end_date,b.side,p.coach_id,p.member_id from boundaries b join public.purchases p
      on p.purchase_date<=b.snapshot and p.expiry_date>=case when b.side='opening' then b.start_date else b.snapshot end
      where (select count(*) from public.session_usages u where u.purchase_id=p.id and u.usage_date<=b.snapshot)<p.total_sessions
      and not exists(select 1 from public.course_terminations t where t.purchase_id=p.id and coalesce(t.correction_posted_on,t.termination_date)<=b.snapshot
        and (t.reversed_at is null or (t.reversed_at at time zone 'Asia/Taipei')::date>b.snapshot))
  ), counts as (
    select o.start_date,o.end_date,o.coach_id,count(*) opening_members,
      count(*) filter(where exists(select 1 from valid_members c where c.side='closing' and c.start_date=o.start_date and c.end_date=o.end_date and c.coach_id=o.coach_id and c.member_id=o.member_id)) retained_members
      from valid_members o where o.side='opening' group by o.start_date,o.end_date,o.coach_id
  ) select coalesce(jsonb_agg(to_jsonb(c)),'[]'::jsonb) into cohorts from counts c;
  return jsonb_build_object('schema_version',49,'start',p_start,'end',p_end,'coaches',performance_private.roster(),'facts',facts,'cohorts',cohorts,
    'hours',coalesce((select jsonb_agg(to_jsonb(h) order by month,coach_id) from performance_private.monthly_hours h
      where month between date_trunc('month',p_start)::date and date_trunc('month',p_end)::date),'[]'::jsonb));
end $$;

create function public.coach_performance_report(p_start date,p_end date) returns jsonb language sql stable security invoker set search_path='' as $$ select performance_private.report(p_start,p_end) $$;
create function public.coach_monthly_work_hours(p_month date) returns jsonb language sql stable security invoker set search_path='' as $$ select performance_private.work_hours(p_month) $$;
create function public.save_coach_monthly_work_hours(p_operation_id uuid,p_month date,p_rows jsonb) returns jsonb language sql security invoker set search_path='' as $$ select performance_private.save_hours(p_operation_id,p_month,p_rows) $$;

revoke all on all functions in schema performance_private from public,anon,authenticated;
grant execute on function performance_private.actor(),performance_private.roster(),performance_private.report(date,date),performance_private.work_hours(date),performance_private.save_hours(uuid,date,jsonb) to authenticated;
revoke all on function public.coach_performance_report(date,date),public.coach_monthly_work_hours(date),public.save_coach_monthly_work_hours(uuid,date,jsonb) from public,anon,authenticated;
grant execute on function public.coach_performance_report(date,date),public.coach_monthly_work_hours(date),public.save_coach_monthly_work_hours(uuid,date,jsonb) to authenticated;
comment on function public.coach_performance_report(date,date) is 'v1.13.49 主管/管理員績效彙總，不回傳會員身分、原始中止或退款明細；不使用排班。';
notify pgrst,'reload schema';
commit;
