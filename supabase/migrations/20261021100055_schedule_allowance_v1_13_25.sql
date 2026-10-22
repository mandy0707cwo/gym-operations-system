-- v25候選：獨立月額度與稽核，不修改班表、營運、金額或審核資料。
create table public.staff_schedule_allowances(
 month_start date primary key check(extract(day from month_start)=1),
 saturday_days integer not null check(saturday_days between 4 and 5),
 holiday_days integer not null check(holiday_days between 0 and 31),
 total_units integer not null check(total_units=(saturday_days+holiday_days)*2),
 holidays jsonb not null check(jsonb_typeof(holidays)='array' and jsonb_array_length(holidays)=holiday_days),
 deduct_units jsonb not null check(deduct_units='{"full_off":2,"half_off":1,"weekend":0,"public_off":2}'::jsonb),
 note text not null default '' check(length(note)<=1000),revision integer not null check(revision>0),
 confirmed_by uuid not null references public.profiles(id),confirmed_name text not null,
 updated_at timestamptz not null default now()
);
create table public.staff_schedule_allowance_logs(
 id uuid primary key default gen_random_uuid(),month_start date not null references public.staff_schedule_allowances(month_start),
 actor_id uuid not null references public.profiles(id),actor_name text not null,
 before_value jsonb,after_value jsonb not null,created_at timestamptz not null default now()
);
create index staff_schedule_allowance_logs_month on public.staff_schedule_allowance_logs(month_start,created_at,id);
alter table public.staff_schedule_allowances enable row level security;
alter table public.staff_schedule_allowance_logs enable row level security;
revoke all on public.staff_schedule_allowances,public.staff_schedule_allowance_logs from public,anon,authenticated,service_role;
grant select on public.staff_schedule_allowances,public.staff_schedule_allowance_logs to authenticated,service_role;
create policy allowance_read on public.staff_schedule_allowances for select to authenticated
 using ((select schedule_private.actor_role()) is not null);
create policy allowance_log_read on public.staff_schedule_allowance_logs for select to authenticated
 using ((select schedule_private.actor_role())='admin');

create function schedule_private.allowance_save(p_operation_id uuid,p_month date,p_expected_revision integer,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid();r text;req schedule_private.requests%rowtype;old public.staff_schedule_allowances%rowtype;
 payload jsonb:=jsonb_build_object('type','allowance','month',p_month,'revision',p_expected_revision,'data',p_payload);
 entries jsonb;units jsonb;entry jsonb;name text;original date;observed date;originals date[]:='{}';observeds date[]:='{}';
 holidays jsonb:='[]';sat integer;note text;actor_name text;result jsonb;
begin
 r:=schedule_private.actor_role();
 if r<>'admin' then raise exception using errcode='42501',message='僅系統管理員可確認排休額度';end if;
 if p_operation_id is null or p_month is null or not isfinite(p_month) or extract(day from p_month)<>1
   or p_month<date '0001-01-01' or p_month>date '9998-12-01' or p_expected_revision is null or p_expected_revision<0
   or p_payload is null or jsonb_typeof(p_payload)<>'object' then raise exception '額度月份、版本或內容無效';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,22));
 select * into req from schedule_private.requests where actor_id=a and operation_id=p_operation_id;
 if found then
  if req.state='cancelled' then raise exception '操作已取消，禁止延遲送出';end if;
  if req.payload is distinct from payload then raise exception '操作識別碼內容不同';end if;
  return req.result;
 end if;
 entries:=p_payload->'holidays';units:=p_payload->'deduct_units';note:=trim(coalesce(p_payload->>'note',''));
 if entries is null or jsonb_typeof(entries)<>'array' then raise exception '假日明細必須為清單';end if;
 if jsonb_array_length(entries)>31 or length(note)>1000 then raise exception '假日明細或備註過長';end if;
 if units is null or jsonb_typeof(units)<>'object' then raise exception '請設定休假扣算方式';end if;
 if (select count(*) from jsonb_object_keys(units))<>4 or not (units ?& array['full_off','half_off','weekend','public_off'])
    or exists(select 1 from jsonb_each(units) v where jsonb_typeof(v.value)<>'number' or v.value::text !~ '^[012]$')
    then raise exception '各班別扣算單位須為0、0.5或1天';end if;
 if units<>'{"full_off":2,"half_off":1,"weekend":0,"public_off":2}'::jsonb then
  raise exception '扣算方式不符已確認規則：整日休1天、半日休0.5天、公休1天，其餘不扣';end if;
 for entry in select value from jsonb_array_elements(entries) loop
  if jsonb_typeof(entry)<>'object' or jsonb_typeof(entry->'name') is distinct from 'string'
    or coalesce(entry->>'original_date','') !~ '^\d{4}-\d{2}-\d{2}$'
    or coalesce(entry->>'observed_date','') !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '假日名稱與日期格式無效';end if;
  name:=trim(entry->>'name');original:=(entry->>'original_date')::date;observed:=(entry->>'observed_date')::date;
  if name='' or length(name)>100 or original<date '0001-01-01' or original>date '9999-12-31'
     or observed<p_month or observed>=p_month+interval '1 month' then raise exception '假日名稱或計入月份無效';end if;
  if extract(isodow from original)>=6 then
   if observed=original or extract(isodow from observed)>=6 then raise exception '週末假日只計入平日補假，不重複原假日';end if;
  elsif observed<>original then raise exception '平日國定假日應計入原日期';end if;
  if original=any(originals) or observed=any(observeds) then raise exception '假日或補假日期重複';end if;
  originals:=array_append(originals,original);observeds:=array_append(observeds,observed);
  holidays:=holidays||jsonb_build_array(jsonb_build_object('name',name,'original_date',original,'observed_date',observed));
 end loop;
 select coalesce(jsonb_agg(value order by value->>'observed_date'),'[]') into holidays from jsonb_array_elements(holidays);
 select count(*) into sat from generate_series(p_month::timestamp,(p_month+interval '1 month'-interval '1 day')::timestamp,interval '1 day') d
  where extract(isodow from d)=6;
 -- 同一原假日不得分別在不同月份重複取得補假額度；跨月確認也須序列化核對。
 perform pg_advisory_xact_lock(hashtextextended('allowance_holidays',25));
 if exists(select 1 from public.staff_schedule_allowances x cross join lateral jsonb_array_elements(x.holidays) h
           where x.month_start<>p_month and (h->>'original_date')::date=any(originals)) then
  raise exception '同一原假日已計入其他月份，請先核對原月份';end if;
 perform pg_advisory_xact_lock(hashtextextended('allowance:'||p_month::text,25));
 select * into old from public.staff_schedule_allowances where month_start=p_month for update;
 if coalesce(old.revision,0)<>p_expected_revision then raise exception '額度已更新，請重新載入';end if;
 select display_name into actor_name from public.profiles where id=a;
 insert into public.staff_schedule_allowances(month_start,saturday_days,holiday_days,total_units,holidays,deduct_units,note,revision,confirmed_by,confirmed_name)
 values(p_month,sat,jsonb_array_length(holidays),(sat+jsonb_array_length(holidays))*2,holidays,units,note,p_expected_revision+1,a,actor_name)
 on conflict(month_start) do update set saturday_days=excluded.saturday_days,holiday_days=excluded.holiday_days,
 total_units=excluded.total_units,holidays=excluded.holidays,deduct_units=excluded.deduct_units,note=excluded.note,
 revision=excluded.revision,confirmed_by=excluded.confirmed_by,confirmed_name=excluded.confirmed_name,updated_at=now();
 select to_jsonb(x) into result from public.staff_schedule_allowances x where month_start=p_month;
 insert into public.staff_schedule_allowance_logs(month_start,actor_id,actor_name,before_value,after_value)
 values(p_month,a,actor_name,case when old.month_start is null then null else to_jsonb(old) end,result);
 result:=result||jsonb_build_object('state','confirmed');
 insert into schedule_private.requests(actor_id,operation_id,state,payload,result) values(a,p_operation_id,'completed',payload,result);
 return result;
end $$;
revoke all on function schedule_private.allowance_save(uuid,date,integer,jsonb) from public,anon,authenticated,service_role;
grant execute on function schedule_private.allowance_save(uuid,date,integer,jsonb) to authenticated;
create function public.staff_schedule_allowance_save(p_operation_id uuid,p_month date,p_expected_revision integer,p_payload jsonb)
returns jsonb language sql security invoker set search_path='' as $$
 select schedule_private.allowance_save(p_operation_id,p_month,p_expected_revision,p_payload);
$$;
create function public.staff_schedule_allowance_snapshot(p_month date) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
begin
 perform schedule_private.actor_role();
 if p_month is null or not isfinite(p_month) or extract(day from p_month)<>1 then raise exception '月份無效';end if;
 return jsonb_build_object('record',(select to_jsonb(x) from public.staff_schedule_allowances x where month_start=p_month));
end $$;
revoke all on function public.staff_schedule_allowance_save(uuid,date,integer,jsonb),public.staff_schedule_allowance_snapshot(date) from public,anon,authenticated,service_role;
grant execute on function public.staff_schedule_allowance_save(uuid,date,integer,jsonb),public.staff_schedule_allowance_snapshot(date) to authenticated;
