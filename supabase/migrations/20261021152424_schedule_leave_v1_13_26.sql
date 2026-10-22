-- v26候選：只新增請假、稽核與班表防衝突；不改任何財務／出勤／獎金數值。
create table public.staff_schedule_leaves(
 id uuid primary key,coach_id uuid not null references public.profiles(id),month_start date not null,work_date date not null,
 leave_kind text not null check(leave_kind in ('annual','sick','personal','other')),
 start_time time not null,end_time time not null,
 minutes integer generated always as ((extract(epoch from (end_time-start_time))/60)::integer) stored,
 state text not null check(state in ('active','void')),revision integer not null check(revision>0),
 reason text not null check(length(trim(reason)) between 1 and 1000),
 actor_id uuid not null references public.profiles(id),actor_name text not null,updated_at timestamptz not null default now(),
 foreign key(coach_id,month_start) references public.staff_schedule_months(coach_id,month_start),
 foreign key(coach_id,work_date) references public.staff_schedule_days(coach_id,work_date),
 check(work_date>=month_start and work_date<month_start+interval '1 month'),
 check(start_time<end_time and end_time<time '24:00' and extract(second from start_time)=0 and extract(second from end_time)=0)
);
create index staff_schedule_leave_month on public.staff_schedule_leaves(month_start,coach_id,work_date,id);
create index staff_schedule_leave_active on public.staff_schedule_leaves(coach_id,work_date,start_time,end_time) where state='active';
create table public.staff_schedule_leave_logs(
 id uuid primary key default gen_random_uuid(),leave_id uuid not null references public.staff_schedule_leaves(id),
 coach_id uuid not null references public.profiles(id),month_start date not null,
 actor_id uuid not null references public.profiles(id),actor_name text not null,action text not null check(action in ('save','void')),
 reason text not null,before_value jsonb,after_value jsonb not null,created_at timestamptz not null default now()
);
create index staff_schedule_leave_log_month on public.staff_schedule_leave_logs(month_start,coach_id,created_at,id);
create index staff_schedule_leave_log_id on public.staff_schedule_leave_logs(leave_id);
alter table public.staff_schedule_leaves enable row level security;
alter table public.staff_schedule_leave_logs enable row level security;
revoke all on public.staff_schedule_leaves,public.staff_schedule_leave_logs from public,anon,authenticated,service_role;
grant select on public.staff_schedule_leaves,public.staff_schedule_leave_logs to authenticated,service_role;
create policy leave_read on public.staff_schedule_leaves for select to authenticated
 using ((select schedule_private.actor_role()) is not null and
        (coach_id=(select auth.uid()) or (select schedule_private.actor_role()) in ('manager','admin')));
create policy leave_log_read on public.staff_schedule_leave_logs for select to authenticated
 using ((select schedule_private.actor_role()) is not null and
        (coach_id=(select auth.uid()) or (select schedule_private.actor_role()) in ('manager','admin')));

-- 安全投影：只為有排班權限的活躍帳號提供核准月份的不在班時段，從不回傳假別／原因。
create function schedule_private.leave_availability(p_month date) returns jsonb
language plpgsql stable security definer set search_path='' as $$
begin
 perform schedule_private.actor_role();
 return (select coalesce(jsonb_agg(jsonb_build_object('coach_id',l.coach_id,'work_date',l.work_date,
  'start_time',l.start_time,'end_time',l.end_time,'minutes',l.minutes) order by l.work_date,l.coach_id,l.start_time),'[]')
  from public.staff_schedule_leaves l join public.staff_schedule_months m using(coach_id,month_start)
  where l.month_start=p_month and l.state='active' and m.state='approved');
end $$;
revoke all on function schedule_private.leave_availability(date) from public,anon,authenticated,service_role;
grant execute on function schedule_private.leave_availability(date) to authenticated;

create function schedule_private.leave_save(p_operation_id uuid,p_id uuid,p_coach_id uuid,p_month date,
 p_expected_revision integer,p_schedule_revision integer,p_action text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid();r text;req schedule_private.requests%rowtype;old public.staff_schedule_leaves%rowtype;
 m public.staff_schedule_months%rowtype;d public.staff_schedule_days%rowtype;
 payload jsonb:=jsonb_build_object('type','leave','id',p_id,'coach',p_coach_id,'month',p_month,
 'revision',p_expected_revision,'schedule_revision',p_schedule_revision,'action',p_action,'data',p_payload);
 work date;s time;e time;kind text;reason text;actor_name text;result jsonb;
begin
 r:=schedule_private.actor_role();
 if r not in ('manager','admin') then raise exception using errcode='42501',message='僅主管或系統管理員可登錄請假';end if;
 if p_operation_id is null or p_id is null or p_coach_id is null or p_month is null or not isfinite(p_month)
   or p_month<date '0001-01-01' or p_month>date '9998-12-01' or extract(day from p_month)<>1
   or p_expected_revision is null or p_expected_revision<0 or p_schedule_revision is null or p_schedule_revision<0
   or p_action is null or p_action not in ('save','void') or p_payload is null or jsonb_typeof(p_payload)<>'object'
   then raise exception '請假月份、版本或內容無效';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,22));
 select * into req from schedule_private.requests where actor_id=a and operation_id=p_operation_id;
 if found then
  if req.state='cancelled' then raise exception '操作已取消，禁止延遲送出';end if;
  if req.payload is distinct from payload then raise exception '操作識別碼內容不同';end if;
  return req.result;
 end if;
 if not exists(select 1 from public.profiles where id=p_coach_id and role='coach' and active) then raise exception '對象不是有效教練';end if;
 perform pg_advisory_xact_lock(hashtextextended('leave:'||p_id::text,26));
 -- 與既有改班共用月份列鎖；同一教練同月的請假／班表更正不能彼此穿透。
 select * into m from public.staff_schedule_months where coach_id=p_coach_id and month_start=p_month for update;
 if not found then raise exception '請先核准本月班表，再登錄請假';end if;
 select * into old from public.staff_schedule_leaves where id=p_id for update;
 if coalesce(old.revision,0)<>p_expected_revision then raise exception '請假已更新，請重新載入';end if;
 if old.id is not null and (old.coach_id<>p_coach_id or old.month_start<>p_month or old.state<>'active') then raise exception '請假紀錄無效或已作廢';end if;
 if jsonb_typeof(p_payload->'reason') is distinct from 'string' then raise exception '請填寫登錄／修改原因';end if;
 reason:=trim(p_payload->>'reason');
 if reason='' or length(reason)>1000 then raise exception '請填寫1000字內的登錄／修改原因';end if;
 if p_action='save' then
  if m.state<>'approved' then raise exception '請先核准本月班表，再登錄請假';end if;
  if m.revision<>p_schedule_revision then raise exception '班表已更新，請重新載入';end if;
  if coalesce(p_payload->>'work_date','') !~ '^\d{4}-\d{2}-\d{2}$'
    or coalesce(p_payload->>'start_time','') !~ '^\d{2}:\d{2}(:00)?$'
    or coalesce(p_payload->>'end_time','') !~ '^\d{2}:\d{2}(:00)?$' then raise exception '請假日期／時段格式無效';end if;
  work:=(p_payload->>'work_date')::date;s:=(p_payload->>'start_time')::time;e:=(p_payload->>'end_time')::time;kind:=p_payload->>'leave_kind';
  if work<p_month or work>=p_month+interval '1 month' or s>=e or e>=time '24:00' or kind is null
    or kind not in ('annual','sick','personal','other') then raise exception '請假日期、假別或時段無效';end if;
  select * into d from public.staff_schedule_days where coach_id=p_coach_id and work_date=work;
  if d.start_time is null or d.end_time is null then raise exception '此日沒有上班時段，不可在已排休時段重複登錄請假';end if;
  if s<d.start_time or e>d.end_time then raise exception '請假須完整落在當日已核准上班時段內';end if;
  if exists(select 1 from public.staff_schedule_leaves l where l.coach_id=p_coach_id and l.work_date=work and l.state='active'
     and l.id<>p_id and s<l.end_time and l.start_time<e) then raise exception '請假時段重疊，不可重複登錄';end if;
 else
  if old.id is null then raise exception '找不到可作廢的請假';end if;
  work:=old.work_date;s:=old.start_time;e:=old.end_time;kind:=old.leave_kind;
 end if;
 select display_name into actor_name from public.profiles where id=a;
 insert into public.staff_schedule_leaves(id,coach_id,month_start,work_date,leave_kind,start_time,end_time,state,revision,reason,actor_id,actor_name)
 values(p_id,p_coach_id,p_month,work,kind,s,e,case when p_action='save' then 'active' else 'void' end,p_expected_revision+1,reason,a,actor_name)
 on conflict(id) do update set work_date=excluded.work_date,leave_kind=excluded.leave_kind,start_time=excluded.start_time,
 end_time=excluded.end_time,state=excluded.state,revision=excluded.revision,reason=excluded.reason,actor_id=excluded.actor_id,
 actor_name=excluded.actor_name,updated_at=now();
 select to_jsonb(x) into result from public.staff_schedule_leaves x where id=p_id;
 insert into public.staff_schedule_leave_logs(leave_id,coach_id,month_start,actor_id,actor_name,action,reason,before_value,after_value)
 values(p_id,p_coach_id,p_month,a,actor_name,p_action,reason,case when old.id is null then null else to_jsonb(old) end,result);
 insert into schedule_private.requests(actor_id,operation_id,state,payload,result) values(a,p_operation_id,'completed',payload,result);
 return result;
end $$;
revoke all on function schedule_private.leave_save(uuid,uuid,uuid,date,integer,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function schedule_private.leave_save(uuid,uuid,uuid,date,integer,integer,text,jsonb) to authenticated;

create function public.staff_schedule_leave_save(p_operation_id uuid,p_id uuid,p_coach_id uuid,p_month date,
 p_expected_revision integer,p_schedule_revision integer,p_action text,p_payload jsonb) returns jsonb
language sql security invoker set search_path='' as $$
 select schedule_private.leave_save(p_operation_id,p_id,p_coach_id,p_month,p_expected_revision,p_schedule_revision,p_action,p_payload);
$$;
create function public.staff_schedule_leave_snapshot(p_month date) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
begin
 perform schedule_private.actor_role();
 if p_month is null or not isfinite(p_month) or extract(day from p_month)<>1 then raise exception '月份無效';end if;
 return jsonb_build_object(
  'records',(select coalesce(jsonb_agg(to_jsonb(x) order by work_date,start_time,id),'[]') from public.staff_schedule_leaves x where month_start=p_month),
  'logs',(select coalesce(jsonb_agg(to_jsonb(x) order by created_at,id),'[]') from public.staff_schedule_leave_logs x where month_start=p_month),
  'availability',schedule_private.leave_availability(p_month));
end $$;
revoke all on function public.staff_schedule_leave_save(uuid,uuid,uuid,date,integer,integer,text,jsonb),public.staff_schedule_leave_snapshot(date)
 from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_leave_save(uuid,uuid,uuid,date,integer,integer,text,jsonb),public.staff_schedule_leave_snapshot(date) to authenticated;

create function schedule_private.guard_leave_day() returns trigger language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.staff_schedule_leaves l where l.coach_id=old.coach_id and l.work_date=old.work_date and l.state='active'
   and (new.coach_id<>old.coach_id or new.work_date<>old.work_date or new.start_time is null or new.end_time is null
        or l.start_time<new.start_time or l.end_time>new.end_time)) then
  raise exception '此日已有有效請假，請先更正或作廢請假，再變更班表';end if;
 return new;
end $$;
revoke all on function schedule_private.guard_leave_day() from public,anon,authenticated,service_role;
create trigger staff_schedule_guard_leave before update on public.staff_schedule_days for each row execute function schedule_private.guard_leave_day();
