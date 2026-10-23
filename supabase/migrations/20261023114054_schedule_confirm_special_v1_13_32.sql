-- v1.13.32：整月確認後鎖定、管理者統一特殊假別。新增來源，不重寫原班表／財務。
begin;
alter table public.staff_schedule_months add column coach_locked boolean not null default false;
alter table public.staff_schedule_months add column finalized_at timestamptz;
alter table public.staff_schedule_months add column finalized_by uuid references public.profiles(id);
-- 舊待審、核准、退回已曾確認；只補鎖定旗標，不虛構歷史確認時間。
update public.staff_schedule_months set coach_locked=true where state in ('submitted','approved','returned');

create function schedule_private.confirm_lock() returns trigger language plpgsql security definer set search_path='' as $$
declare r text:=schedule_private.actor_role();
begin
 if tg_op='UPDATE' and old.coach_locked and r='coach' then
  raise exception using errcode='42501',message='本月已確認儲存，只有主管及管理者可修改，教練不能撤回或因退回而解鎖';
 end if;
 if tg_op='UPDATE' and old.coach_locked and not new.coach_locked then raise exception '已確認班表不可解除教練鎖定';end if;
 if r='coach' and new.state='submitted' then
  new.coach_locked:=true;new.finalized_at:=coalesce(new.finalized_at,now());new.finalized_by:=coalesce(new.finalized_by,auth.uid());
 end if;
 return new;
end $$;
revoke all on function schedule_private.confirm_lock() from public,anon,authenticated,service_role;
create trigger schedule_confirm_lock before insert or update on public.staff_schedule_months
 for each row execute function schedule_private.confirm_lock();

-- 沿用原交易與收據；只收斂舊可編輯判斷及說明，舊回覆重播仍先回原結果。
do $migration$
declare definition text;
 old_guard text := $old$if r='coach' and m.state not in ('draft','returned') then raise exception '送審或核准後不可修改，請先撤回或由主管退回';end if;$old$;
 new_guard text := $new$if r='coach' and (m.coach_locked or m.state not in ('draft','returned')) then raise exception '本月已確認儲存，教練不可修改，只有主管及管理者可修改';end if;$new$;
begin
 definition:=pg_get_functiondef('schedule_private.command(uuid,uuid,date,integer,text,jsonb)'::regprocedure);
 if strpos(definition,old_guard)=0 then raise exception '排班函式版本不符，停止升級';end if;
 execute replace(definition,old_guard,new_guard);
end $migration$;

create function schedule_private.public_off_guard() returns trigger language plpgsql security definer set search_path='' as $$
begin
 if schedule_private.actor_role()='coach' and (new.shift_code='public_off' or (tg_op='UPDATE' and old.shift_code='public_off')) then
  raise exception using errcode='42501',message='公休須由主管及管理者設定';
 end if;return new;
end $$;
revoke all on function schedule_private.public_off_guard() from public,anon,authenticated,service_role;
create trigger schedule_public_off_guard before insert or update on public.staff_schedule_days
 for each row execute function schedule_private.public_off_guard();

create function schedule_private.manager_confirm(p_operation_id uuid,p_coach_id uuid,p_month date,
 p_expected_revision integer,p_action text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid();r text:=schedule_private.actor_role();m public.staff_schedule_months%rowtype;
 q schedule_private.requests%rowtype;before_value jsonb;result jsonb;actor_name text;
 reason text:=trim(coalesce(p_payload->>'reason',''));
 payload jsonb:=jsonb_build_object('kind','manager_confirm','coach',p_coach_id,'month',p_month,'revision',p_expected_revision,'data',p_payload);
begin
 if r not in ('manager','admin') then raise exception using errcode='42501',message='僅主管及管理者可代填完成並核准';end if;
 if p_operation_id is null or p_coach_id is null or p_month is null or not isfinite(p_month) or extract(day from p_month)<>1
  or p_action is distinct from 'manager_confirm' or p_expected_revision is null or p_expected_revision<0
  or p_payload is null or jsonb_typeof(p_payload)<>'object' or reason='' or length(reason)>1000 then raise exception '月份、版本或原因無效';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,22));
 select * into q from schedule_private.requests where actor_id=a and operation_id=p_operation_id;
 if found then
  if q.state='cancelled' then raise exception '操作已取消';end if;
  if q.payload is distinct from payload then raise exception '操作識別碼內容不同';end if;return q.result;
 end if;
 if not exists(select 1 from public.profiles where id=p_coach_id and active and role='coach') then raise exception '排班對象不是有效教練';end if;
 select * into m from public.staff_schedule_months where coach_id=p_coach_id and month_start=p_month for update;
 if not found or m.revision<>p_expected_revision then raise exception '班表已更新或尚未建立，請重新載入';end if;
 if (select count(*) from public.staff_schedule_days where coach_id=p_coach_id and month_start=p_month)
  <>extract(day from p_month+interval '1 month'-interval '1 day') then raise exception '整月尚有未填日期';end if;
 before_value:=to_jsonb(m);
 update public.staff_schedule_months set state='approved',coach_locked=true,
  finalized_at=case when coach_locked then finalized_at else now() end,
  finalized_by=case when coach_locked then finalized_by else a end,
  reviewed_by=a,reviewed_at=now(),review_reason=reason,revision=revision+1,updated_at=now()
  where coach_id=p_coach_id and month_start=p_month returning * into m;
 select display_name into actor_name from public.profiles where id=a;
 insert into public.staff_schedule_logs(coach_id,month_start,action,actor_id,actor_name,reason,before_value,after_value)
  values(p_coach_id,p_month,'manager_confirm',a,actor_name,reason,before_value,to_jsonb(m));
 result:=jsonb_build_object('coach_id',p_coach_id,'month_start',p_month,'state',m.state,'revision',m.revision,'action',p_action);
 insert into schedule_private.requests(actor_id,operation_id,payload,result,state) values(a,p_operation_id,payload,result,'completed');
 return result;
end $$;
revoke all on function schedule_private.manager_confirm(uuid,uuid,date,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function schedule_private.manager_confirm(uuid,uuid,date,integer,text,jsonb) to authenticated;
create function public.staff_schedule_manager_confirm(p_operation_id uuid,p_coach_id uuid,p_month date,
 p_expected_revision integer,p_action text,p_payload jsonb) returns jsonb language sql security invoker set search_path='' as $$
 select schedule_private.manager_confirm(p_operation_id,p_coach_id,p_month,p_expected_revision,p_action,p_payload);
$$;
revoke all on function public.staff_schedule_manager_confirm(uuid,uuid,date,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_manager_confirm(uuid,uuid,date,integer,text,jsonb) to authenticated;

create table public.staff_schedule_special_months(
 month_start date primary key check(isfinite(month_start) and extract(day from month_start)=1),
 revision integer not null default 0 check(revision>=0),updated_at timestamptz not null default now(),
 updated_by uuid not null references public.profiles(id)
);
create table public.staff_schedule_special_days(
 work_date date primary key check(isfinite(work_date)),
 month_start date not null references public.staff_schedule_special_months(month_start),
 kind text not null check(kind in ('public_off','typhoon','spring','banquet','other')),
 label text not null check(length(trim(label)) between 1 and 100),start_time time,end_time time,
 deduct_units integer not null check(deduct_units in (0,1,2)),
 state text not null check(state in ('active','void')),
 check(work_date>=month_start and work_date<month_start+interval '1 month'),
 check(start_time is null and end_time is null)
);
create index schedule_special_month_idx on public.staff_schedule_special_days(month_start,work_date);
create table schedule_private.special_logs(
 id uuid primary key default gen_random_uuid(),month_start date not null,actor_id uuid not null references public.profiles(id),
 action text not null,reason text not null,before_value jsonb,after_value jsonb,created_at timestamptz not null default now()
);
alter table public.staff_schedule_special_months enable row level security;
alter table public.staff_schedule_special_days enable row level security;
alter table schedule_private.special_logs enable row level security;
revoke all on public.staff_schedule_special_months,public.staff_schedule_special_days,schedule_private.special_logs from public,anon,authenticated,service_role;
grant select on public.staff_schedule_special_months,public.staff_schedule_special_days to authenticated;
grant select on public.staff_schedule_special_months,public.staff_schedule_special_days to service_role;
create policy schedule_special_month_read on public.staff_schedule_special_months for select to authenticated
 using ((select schedule_private.actor_role()) is not null);
create policy schedule_special_day_read on public.staff_schedule_special_days for select to authenticated
 using ((select schedule_private.actor_role()) is not null);

create function public.staff_schedule_special_snapshot(p_month date) returns jsonb
language plpgsql security invoker set search_path='' as $$
begin
 perform schedule_private.actor_role();
 if p_month is null or not isfinite(p_month) or extract(day from p_month)<>1 then raise exception '月份無效';end if;
 return jsonb_build_object('revision',coalesce((select revision from public.staff_schedule_special_months where month_start=p_month),0),
  'days',coalesce((select jsonb_agg(to_jsonb(d) order by work_date) from public.staff_schedule_special_days d where month_start=p_month),'[]'::jsonb))
 ;
end;
$$;
revoke all on function public.staff_schedule_special_snapshot(date) from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_special_snapshot(date) to authenticated;

create function schedule_private.special_save(p_operation_id uuid,p_month date,p_expected_revision integer,
 p_action text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid();r text:=schedule_private.actor_role();q schedule_private.requests%rowtype;
 rev integer;d1 date;d2 date;k text;label text;s time;e time;units integer;before_value jsonb;after_value jsonb;result jsonb;
 reason text:=trim(coalesce(p_payload->>'reason',''));
 payload jsonb:=jsonb_build_object('kind','special','month',p_month,'revision',p_expected_revision,'action',p_action,'data',p_payload);
begin
 if r not in ('manager','admin') then raise exception using errcode='42501',message='僅主管及管理者可設定特殊假別';end if;
 if p_operation_id is null or p_month is null or not isfinite(p_month) or extract(day from p_month)<>1
  or p_expected_revision is null or p_expected_revision<0 or p_action is null or p_action not in ('save','void')
  or p_payload is null or jsonb_typeof(p_payload)<>'object' or reason='' or length(reason)>1000 then raise exception '月份、版本、動作或原因無效';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,22));
 select * into q from schedule_private.requests where actor_id=a and operation_id=p_operation_id;
 if found then
  if q.state='cancelled' then raise exception '操作已取消';end if;
  if q.payload is distinct from payload then raise exception '操作識別碼內容不同';end if;return q.result;
 end if;
 d1:=(p_payload->>'date_from')::date;d2:=(p_payload->>'date_to')::date;
 if d1 is null or d2 is null or not isfinite(d1) or not isfinite(d2) or d1>d2 or d1<p_month or d2>=p_month+interval '1 month' then raise exception '日期起迄須在目前月份';end if;
 if p_action='save' then
  k:=p_payload->>'kind';label:=trim(coalesce(p_payload->>'label',''));
  if k is null or k not in ('public_off','typhoon','spring','banquet','other') or length(label) not between 1 and 100 then raise exception '假別或名稱無效';end if;
  if jsonb_typeof(p_payload->'deduct_units') is distinct from 'number' or p_payload->>'deduct_units' not in ('0','1','2') then raise exception '請明確指定該日扣額度0、0.5或1天';end if;
  units:=(p_payload->>'deduct_units')::integer;
  s:=nullif(p_payload->>'start_time','')::time;e:=nullif(p_payload->>'end_time','')::time;
  if s is not null or e is not null then raise exception '本版特殊假別僅支援整日休';end if;
 end if;
 insert into public.staff_schedule_special_months(month_start,updated_by) values(p_month,a) on conflict do nothing;
 select revision into rev from public.staff_schedule_special_months where month_start=p_month for update;
 if rev<>p_expected_revision then raise exception '特殊假別已更新，請重新載入';end if;
 select coalesce(jsonb_agg(to_jsonb(x) order by work_date),'[]') into before_value
  from public.staff_schedule_special_days x where work_date between d1 and d2;
 if p_action='save' then
  insert into public.staff_schedule_special_days(work_date,month_start,kind,label,start_time,end_time,deduct_units,state)
   select d::date,p_month,k,label,s,e,units,'active' from generate_series(d1::timestamp,d2::timestamp,interval '1 day') d
   on conflict(work_date) do update set kind=excluded.kind,label=excluded.label,start_time=excluded.start_time,
    end_time=excluded.end_time,deduct_units=excluded.deduct_units,state='active';
 else
  if not exists(select 1 from public.staff_schedule_special_days where work_date between d1 and d2 and state='active') then raise exception '所選日期沒有有效特殊假別';end if;
  update public.staff_schedule_special_days set state='void' where work_date between d1 and d2 and state='active';
 end if;
 update public.staff_schedule_special_months set revision=revision+1,updated_by=a,updated_at=now() where month_start=p_month returning revision into rev;
 select coalesce(jsonb_agg(to_jsonb(x) order by work_date),'[]') into after_value
  from public.staff_schedule_special_days x where work_date between d1 and d2;
 insert into schedule_private.special_logs(month_start,actor_id,action,reason,before_value,after_value)
  values(p_month,a,p_action,reason,before_value,after_value);
 result:=jsonb_build_object('month_start',p_month,'revision',rev,'state','confirmed','action',p_action);
 insert into schedule_private.requests(actor_id,operation_id,payload,result,state) values(a,p_operation_id,payload,result,'completed');
 return result;
end $$;
revoke all on function schedule_private.special_save(uuid,date,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function schedule_private.special_save(uuid,date,integer,text,jsonb) to authenticated;
create function public.staff_schedule_special_save(p_operation_id uuid,p_month date,p_expected_revision integer,
 p_action text,p_payload jsonb) returns jsonb language sql security invoker set search_path='' as $$
 select schedule_private.special_save(p_operation_id,p_month,p_expected_revision,p_action,p_payload);
$$;
revoke all on function public.staff_schedule_special_save(uuid,date,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_special_save(uuid,date,integer,text,jsonb) to authenticated;
commit;
