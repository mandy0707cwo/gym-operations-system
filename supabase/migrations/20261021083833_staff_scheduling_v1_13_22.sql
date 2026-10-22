-- v1.13.22 候選：只新增排班資料與RPC，不修改既有營運／財務資料。
create schema schedule_private;
revoke all on schema schedule_private from public,anon,authenticated,service_role;
grant usage on schema schedule_private to authenticated;

create table public.staff_schedule_months(
 coach_id uuid not null references public.profiles(id), month_start date not null,
 coach_name text not null, state text not null default 'draft' check(state in ('draft','submitted','approved','returned')),
 revision integer not null default 0 check(revision>=0), reviewed_by uuid references public.profiles(id),
 reviewed_at timestamptz,review_reason text not null default '',updated_at timestamptz not null default now(),
 primary key(coach_id,month_start),check(extract(day from month_start)=1)
);
create index staff_schedule_month_date on public.staff_schedule_months(month_start,coach_id);
create table public.staff_schedule_days(
 coach_id uuid not null,month_start date not null,work_date date not null,
 shift_code text not null check(shift_code in ('A','B','C','full_off','half_off','weekend','regular_off','public_off','other')),
 start_time time,end_time time,note text not null default '' check(length(note)<=1000),
 primary key(coach_id,work_date),foreign key(coach_id,month_start) references public.staff_schedule_months(coach_id,month_start),
 check(work_date>=month_start and work_date<month_start+interval '1 month'),
 check((shift_code='A' and start_time is not null and end_time is not null and start_time=time '09:00' and end_time=time '18:00')
 or (shift_code='B' and start_time is not null and end_time is not null and start_time=time '12:00' and end_time=time '21:00')
 or (shift_code in ('C','half_off') and start_time is not null and end_time is not null and start_time<end_time)
 or (shift_code in ('full_off','weekend','regular_off','public_off') and start_time is null and end_time is null)
 or (shift_code='other' and length(trim(note))>0 and ((start_time is null and end_time is null)
       or (start_time is not null and end_time is not null and start_time<end_time)))),
 check((start_time is null or extract(second from start_time)=0) and (end_time is null or (extract(second from end_time)=0 and end_time<time '24:00')))
);
create index staff_schedule_days_month on public.staff_schedule_days(month_start,coach_id,work_date);
create table public.staff_schedule_preferences(
 coach_id uuid primary key references public.profiles(id),base_shift text not null check(base_shift in ('A','B')),
 updated_at timestamptz not null default now()
);
create table public.staff_schedule_logs(
 id uuid primary key default gen_random_uuid(),coach_id uuid not null references public.profiles(id),
 month_start date not null,action text not null,actor_id uuid not null references public.profiles(id),
 actor_name text not null,reason text not null default '',before_value jsonb,after_value jsonb,
 created_at timestamptz not null default now()
);
create index staff_schedule_logs_month on public.staff_schedule_logs(month_start,coach_id,created_at,id);
create table schedule_private.requests(
 actor_id uuid not null,operation_id uuid not null,payload jsonb,result jsonb,
 state text not null check(state in ('completed','cancelled')),created_at timestamptz not null default now(),
 primary key(actor_id,operation_id)
);
alter table schedule_private.requests enable row level security;
revoke all on schedule_private.requests from public,anon,authenticated,service_role;

create function schedule_private.actor_role() returns text language plpgsql security definer set search_path='' as $$
declare r text;
begin
 select role::text into r from public.profiles where id=auth.uid() and active and role in ('coach','manager','admin');
 if r is null then raise exception using errcode='42501',message='帳號無排班權限、已停用或不存在';end if;
 return r;
end $$;
revoke all on function schedule_private.actor_role() from public,anon,authenticated,service_role;
grant execute on function schedule_private.actor_role() to authenticated;

alter table public.staff_schedule_months enable row level security;
alter table public.staff_schedule_days enable row level security;
alter table public.staff_schedule_preferences enable row level security;
alter table public.staff_schedule_logs enable row level security;
revoke all on public.staff_schedule_months,public.staff_schedule_days,public.staff_schedule_preferences,public.staff_schedule_logs
 from public,anon,authenticated,service_role;
grant select on public.staff_schedule_months,public.staff_schedule_days,public.staff_schedule_preferences,public.staff_schedule_logs to authenticated;
grant select on public.staff_schedule_months,public.staff_schedule_days,public.staff_schedule_preferences,public.staff_schedule_logs to service_role;
create policy schedule_month_read on public.staff_schedule_months for select to authenticated using ((select schedule_private.actor_role()) is not null);
create policy schedule_day_read on public.staff_schedule_days for select to authenticated using ((select schedule_private.actor_role()) is not null);
create policy schedule_preference_read on public.staff_schedule_preferences for select to authenticated using ((select schedule_private.actor_role()) is not null);
create policy schedule_log_read on public.staff_schedule_logs for select to authenticated
 using ((select schedule_private.actor_role()) is not null and
        (coach_id=(select auth.uid()) or (select schedule_private.actor_role()) in ('manager','admin')));

create function schedule_private.control(p_operation_id uuid,p_cancel boolean default false) returns jsonb
language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid();r schedule_private.requests%rowtype;
begin
 perform schedule_private.actor_role();
 if p_operation_id is null then raise exception '操作識別碼不可空白';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,22));
 select * into r from schedule_private.requests where actor_id=a and operation_id=p_operation_id;
 if found then return jsonb_build_object('state',r.state,'result',r.result);end if;
 if p_cancel then
  insert into schedule_private.requests(actor_id,operation_id,state) values(a,p_operation_id,'cancelled');
  return jsonb_build_object('state','cancelled');
 end if;
 return jsonb_build_object('state','not_found');
end $$;

create function schedule_private.command(p_operation_id uuid,p_coach_id uuid,p_month date,
 p_expected_revision integer,p_action text,p_payload jsonb default '{}'::jsonb) returns jsonb
language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid();r text;name text;actor_name text;req schedule_private.requests%rowtype;
 m public.staff_schedule_months%rowtype;before_month jsonb;before_data jsonb;after_data jsonb;result jsonb;
 payload jsonb:=jsonb_build_object('coach',p_coach_id,'month',p_month,'revision',p_expected_revision,'action',p_action,'data',p_payload);
 reason text:=trim(coalesce(p_payload->>'reason',''));base text;d date;code text;s time;e time;note text;
begin
 r:=schedule_private.actor_role();
 if p_operation_id is null or p_coach_id is null or p_month is null or not isfinite(p_month)
    or extract(day from p_month)<>1 or p_expected_revision is null or p_expected_revision<0
    or p_payload is null or jsonb_typeof(p_payload)<>'object' then raise exception '月份、版本與操作內容無效';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,22));
 select * into req from schedule_private.requests where actor_id=a and operation_id=p_operation_id;
 if found then
  if req.state='cancelled' then raise exception '操作已取消，禁止延遲送出';end if;
  if req.payload is distinct from payload then raise exception '操作識別碼內容不同，請先查核原結果';end if;
  return req.result;
 end if;
 if r='coach' and a<>p_coach_id then raise exception using errcode='42501',message='教練只能修改自己的班表';end if;
 select display_name into name from public.profiles where id=p_coach_id and role='coach' and active;
 if name is null then raise exception '排班對象不是有效教練';end if;
 select display_name into actor_name from public.profiles where id=a;
 insert into public.staff_schedule_months(coach_id,month_start,coach_name) values(p_coach_id,p_month,name) on conflict do nothing;
 select * into m from public.staff_schedule_months where coach_id=p_coach_id and month_start=p_month for update;
 if m.revision<>p_expected_revision then raise exception '班表已更新，請重新載入後再操作';end if;
 before_month:=to_jsonb(m);
 if p_action in ('save','fill','default') then
  if r='coach' and m.state not in ('draft','returned') then raise exception '送審或核准後不可修改，請先撤回或由主管退回';end if;
  if r in ('manager','admin') and reason='' then raise exception '主管或管理員更正須填寫原因';end if;
  if p_action='default' then
   base:=p_payload->>'base_shift';
   if base is null or base not in ('A','B') then raise exception '請選擇A班或B班';end if;
   select to_jsonb(x) into before_data from public.staff_schedule_preferences x where coach_id=p_coach_id;
   insert into public.staff_schedule_preferences(coach_id,base_shift) values(p_coach_id,base)
    on conflict(coach_id) do update set base_shift=excluded.base_shift,updated_at=now();
   after_data:=jsonb_build_object('base_shift',base);
  elsif p_action='fill' then
   select base_shift into base from public.staff_schedule_preferences where coach_id=p_coach_id for share;
   if base is null then raise exception '請先儲存A班或B班預設';end if;
   if p_payload->>'base_shift' is distinct from base then raise exception '預設班別已變更，請重新載入';end if;
   before_data:='[]'::jsonb;
   with added as (
    insert into public.staff_schedule_days(coach_id,month_start,work_date,shift_code,start_time,end_time)
    select p_coach_id,p_month,g::date,
      case when extract(isodow from g)=7 then 'regular_off' else base end,
      case when extract(isodow from g)=7 then null when base='A' then time '09:00' else time '12:00' end,
      case when extract(isodow from g)=7 then null when base='A' then time '18:00' else time '21:00' end
    from generate_series(p_month::timestamp,(p_month+interval '1 month'-interval '1 day')::timestamp,interval '1 day') g
    on conflict(coach_id,work_date) do nothing returning *
   ) select coalesce(jsonb_agg(to_jsonb(added)),'[]') into after_data from added;
  else
   d:=(p_payload->>'work_date')::date;code:=p_payload->>'shift_code';note:=trim(coalesce(p_payload->>'note',''));
   if d is null or not isfinite(d) or d<p_month or d>=p_month+interval '1 month' then raise exception '日期不在目前月份';end if;
   if code is null or code not in ('A','B','C','full_off','half_off','weekend','regular_off','public_off','other') then raise exception '班別無效';end if;
   s:=nullif(p_payload->>'start_time','')::time;e:=nullif(p_payload->>'end_time','')::time;
   if code='A' then s:=time '09:00';e:=time '18:00';
   elsif code='B' then s:=time '12:00';e:=time '21:00';
   elsif code in ('full_off','weekend','regular_off','public_off') then s:=null;e:=null;end if;
   if code in ('C','half_off') and (s is null or e is null) then raise exception '此班別須填寫上班時段';end if;
   if (s is null)<>(e is null) or (s is not null and s>=e) then raise exception '上班時段錯誤，本版不跨日';end if;
   if code='other' and note='' then raise exception '其他班別請填寫說明';end if;
   select to_jsonb(x) into before_data from public.staff_schedule_days x where coach_id=p_coach_id and work_date=d;
   insert into public.staff_schedule_days(coach_id,month_start,work_date,shift_code,start_time,end_time,note)
    values(p_coach_id,p_month,d,code,s,e,note) on conflict(coach_id,work_date) do update
    set shift_code=excluded.shift_code,start_time=excluded.start_time,end_time=excluded.end_time,note=excluded.note;
   select to_jsonb(x) into after_data from public.staff_schedule_days x where coach_id=p_coach_id and work_date=d;
  end if;
 elsif p_action='submit' then
  if r<>'coach' or a<>p_coach_id or m.state not in ('draft','returned') then raise exception '僅本人可送審草稿或退回的班表';end if;
  if (select count(*) from public.staff_schedule_days where coach_id=p_coach_id and month_start=p_month)
     <>extract(day from p_month+interval '1 month'-interval '1 day') then raise exception '整月尚有未填日期，請先補齊';end if;
  m.state:='submitted';m.reviewed_by:=null;m.reviewed_at:=null;m.review_reason:='';
 elsif p_action='withdraw' then
  if r<>'coach' or a<>p_coach_id or m.state<>'submitted' then raise exception '只能撤回自己的待審班表';end if;
  m.state:='draft';
 elsif p_action in ('approve','return') then
  if r not in ('manager','admin') then raise exception using errcode='42501',message='僅主管或系統管理員可審核';end if;
  if p_action='approve' and m.state<>'submitted' then raise exception '僅待審班表可核准';end if;
  if p_action='return' and (m.state not in ('submitted','approved') or reason='') then raise exception '退回須為待審或已核准班表並填寫原因';end if;
  m.state:=case when p_action='approve' then 'approved' else 'returned' end;
  m.reviewed_by:=a;m.reviewed_at:=now();m.review_reason:=reason;
 else raise exception '不支援的排班操作';end if;
 if length(reason)>1000 then raise exception '原因不可超過1000字';end if;
 update public.staff_schedule_months set state=m.state,revision=revision+1,reviewed_by=m.reviewed_by,
  reviewed_at=m.reviewed_at,review_reason=m.review_reason,updated_at=now()
  where coach_id=p_coach_id and month_start=p_month returning * into m;
 insert into public.staff_schedule_logs(coach_id,month_start,action,actor_id,actor_name,reason,before_value,after_value)
 values(p_coach_id,p_month,p_action,a,actor_name,reason,
   jsonb_build_object('month',before_month,'data',before_data),jsonb_build_object('month',to_jsonb(m),'data',after_data));
 result:=jsonb_build_object('coach_id',p_coach_id,'month_start',p_month,'state',m.state,'revision',m.revision,'action',p_action);
 insert into schedule_private.requests(actor_id,operation_id,payload,result,state) values(a,p_operation_id,payload,result,'completed');
 return result;
end $$;
revoke all on function schedule_private.command(uuid,uuid,date,integer,text,jsonb) from public,anon,authenticated,service_role;
revoke all on function schedule_private.control(uuid,boolean) from public,anon,authenticated,service_role;
grant execute on function schedule_private.command(uuid,uuid,date,integer,text,jsonb),schedule_private.control(uuid,boolean) to authenticated;
create function public.staff_schedule_command(p_operation_id uuid,p_coach_id uuid,p_month date,p_expected_revision integer,p_action text,p_payload jsonb default '{}'::jsonb)
returns jsonb language sql security invoker set search_path='' as $$
 select schedule_private.command(p_operation_id,p_coach_id,p_month,p_expected_revision,p_action,p_payload);
$$;
create function public.staff_schedule_operation(p_operation_id uuid,p_cancel boolean default false)
returns jsonb language sql security invoker set search_path='' as $$select schedule_private.control(p_operation_id,p_cancel);$$;
revoke all on function public.staff_schedule_command(uuid,uuid,date,integer,text,jsonb),public.staff_schedule_operation(uuid,boolean) from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_command(uuid,uuid,date,integer,text,jsonb),public.staff_schedule_operation(uuid,boolean) to authenticated;
create function public.staff_schedule_snapshot(p_month date) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
begin
 perform schedule_private.actor_role();
 if p_month is null or not isfinite(p_month) or extract(day from p_month)<>1 then raise exception '請使用月份第一日';end if;
 -- 同一SELECT取得整月一致快照，不受REST逐表分頁時間差或1000筆上限影響。
 return jsonb_build_object(
  'coaches',(select coalesce(jsonb_agg(jsonb_build_object('id',p.id,'display_name',p.display_name,'active',p.active,'role',p.role) order by p.display_name,p.id),'[]')
             from public.profiles p where p.role='coach' and p.active),
  'months',(select coalesce(jsonb_agg(to_jsonb(m) order by m.coach_id),'[]') from public.staff_schedule_months m where m.month_start=p_month),
  'days',(select coalesce(jsonb_agg(to_jsonb(d) order by d.work_date,d.coach_id),'[]') from public.staff_schedule_days d where d.month_start=p_month),
  'preferences',(select coalesce(jsonb_agg(to_jsonb(f) order by f.coach_id),'[]') from public.staff_schedule_preferences f));
end $$;
revoke all on function public.staff_schedule_snapshot(date) from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_snapshot(date) to authenticated;
notify pgrst,'reload schema';
