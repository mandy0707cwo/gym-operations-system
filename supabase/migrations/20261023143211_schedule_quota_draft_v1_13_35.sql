-- v35：教練需核定月額度，預排整批原子儲存／送出，沿用既有操作收據、版本鎖及RLS。
begin;
set local lock_timeout='10s';
create or replace function schedule_private.assert_quota(p_coach uuid,p_month date) returns void
language plpgsql security invoker set search_path='' as $$
declare allowance public.staff_schedule_allowances%rowtype;used integer;
begin
 -- 與額度更新互斥；不把「尚未發布」誤當0天。權限仍由command的實際角色檢查。
 select * into allowance from public.staff_schedule_allowances where month_start=p_month for share;
 if not found then raise exception '本月排休額度尚未核定，教練不能排班或儲存';end if;
 select coalesce(sum(coalesce(s.deduct_units,(allowance.deduct_units->>d.shift_code)::integer,0)),0)
 into used from public.staff_schedule_days d left join public.staff_schedule_special_days s
 on s.work_date=d.work_date and s.state='active'
 where d.coach_id=p_coach and d.month_start=p_month;
 if used>allowance.total_units then raise exception '超出本月排休額度，不能儲存草稿或送出';end if;
end $$;
revoke all on function schedule_private.assert_quota(uuid,date) from public,anon,authenticated,service_role;

do $migration$
declare definition text;
 marker text:='-- v35: atomic coach draft';
 old_branch text:=$old$if p_action in ('save','fill','default','apply') then$old$;
 new_branch text:=$new$-- v35: atomic coach draft
 if p_action in ('draft','draft_submit') then
  if r<>'coach' or m.coach_locked or m.state not in ('draft','returned') then
   raise exception using errcode='42501',message='僅教練可儲存自己的未鎖定草稿';end if;
  if jsonb_typeof(p_payload->'days') is distinct from 'array' then raise exception '預排日期須為清單';end if;
  if jsonb_array_length(p_payload->'days')>31 then raise exception '預排最多31筆';end if;
  if (select count(distinct v->>'work_date') from jsonb_array_elements(p_payload->'days') v)
     <>jsonb_array_length(p_payload->'days') then raise exception '預排日期重複或缺漏';end if;
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into before_data from public.staff_schedule_days x
   where coach_id=p_coach_id and month_start=p_month;
  for draft_day in select value from jsonb_array_elements(p_payload->'days') loop
   if jsonb_typeof(draft_day)<>'object' or coalesce(draft_day->>'work_date','') !~ '^\d{4}-\d{2}-\d{2}$' then raise exception '預排日期格式無效';end if;
   d:=(draft_day->>'work_date')::date;code:=draft_day->>'shift_code';note:=trim(coalesce(draft_day->>'note',''));
   if not isfinite(d) or d<p_month or d>=p_month+interval '1 month' then raise exception '日期不在目前月份';end if;
   if code is null or code not in ('A','B','C','full_off','half_off','regular_off','other') then raise exception '班別無效或須由主管設定';end if;
   if length(note)>1000 or (code='other' and note='') then raise exception '備註過長或其他班別缺少說明';end if;
   s:=nullif(draft_day->>'start_time','')::time;e:=nullif(draft_day->>'end_time','')::time;
   if code='A' then s:=time '09:00';e:=time '18:00';
   elsif code='B' then s:=time '12:00';e:=time '21:00';
   elsif code in ('full_off','regular_off') then s:=null;e:=null;end if;
   if code in ('C','half_off') and (s is null or e is null) then raise exception '此班別須填寫上班時段';end if;
   if (s is null)<>(e is null) or (s is not null and (s>=e or extract(second from s)<>0 or extract(second from e)<>0)) then raise exception '上班時段錯誤，本版不跨日';end if;
   insert into public.staff_schedule_days(coach_id,month_start,work_date,shift_code,start_time,end_time,note)
    values(p_coach_id,p_month,d,code,s,e,note) on conflict(coach_id,work_date) do update
    set shift_code=excluded.shift_code,start_time=excluded.start_time,end_time=excluded.end_time,note=excluded.note;
  end loop;
  if p_payload ? 'base_shift' then
   base:=p_payload->>'base_shift';if base is null or base not in ('A','B') then raise exception '預設班別無效';end if;
   insert into public.staff_schedule_preferences(coach_id,base_shift) values(p_coach_id,base)
    on conflict(coach_id) do update set base_shift=excluded.base_shift,updated_at=now();
  end if;
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into after_data from public.staff_schedule_days x
   where coach_id=p_coach_id and month_start=p_month;
  if p_action='draft_submit' then
   if jsonb_array_length(after_data)<>extract(day from p_month+interval '1 month'-interval '1 day') then raise exception '整月尚有未填日期';end if;
   m.state:='submitted';m.reviewed_by:=null;m.reviewed_at:=null;m.review_reason:='';
  end if;
 elsif p_action in ('save','fill','default','apply') then$new$;
 old_end text:=$old$if length(reason)>1000 then raise exception '原因不可超過1000字';end if;$old$;
 new_end text:=$new$if r='coach' and p_action in ('draft','draft_submit','save','fill','default','apply','submit') then
  perform schedule_private.assert_quota(p_coach_id,p_month);
 end if;
 if length(reason)>1000 then raise exception '原因不可超過1000字';end if;$new$;
begin
 definition:=pg_get_functiondef('schedule_private.command(uuid,uuid,date,integer,text,jsonb)'::regprocedure);
 if strpos(definition,marker)>0 then return;end if;
 if strpos(definition,'-- v33:')=0 or strpos(definition,old_branch)=0 or strpos(definition,old_end)=0 then raise exception '需先完成v32及v33升級，停止變更';end if;
 definition:=replace(definition,'note text;','note text;draft_day jsonb;');
 if strpos(definition,'draft_day jsonb;')=0 then raise exception '排班變數版本不符';end if;
 definition:=replace(definition,old_branch,new_branch);
 definition:=replace(definition,old_end,new_end);
 execute definition;
end $migration$;
commit;
