-- v27候選：新增apply動作，一次交易儲存預設與補齊空白，不改舊migration與任何財務數值。
create or replace function schedule_private.command(p_operation_id uuid,p_coach_id uuid,p_month date,
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
 if p_action in ('save','fill','default','apply') then
  if r='coach' and m.state not in ('draft','returned') then raise exception '送審或核准後不可修改，請先撤回或由主管退回';end if;
  if r in ('manager','admin') and reason='' then raise exception '主管或管理員更正須填寫原因';end if;
  if p_action='default' then
   base:=p_payload->>'base_shift';
   if base is null or base not in ('A','B') then raise exception '請選擇A班或B班';end if;
   select to_jsonb(x) into before_data from public.staff_schedule_preferences x where coach_id=p_coach_id;
   insert into public.staff_schedule_preferences(coach_id,base_shift) values(p_coach_id,base)
    on conflict(coach_id) do update set base_shift=excluded.base_shift,updated_at=now();
   after_data:=jsonb_build_object('base_shift',base);
  elsif p_action in ('fill','apply') then
   if p_action='apply' then
    base:=p_payload->>'base_shift';
    if base is null or base not in ('A','B') then raise exception '請選擇A班或B班';end if;
    select to_jsonb(x) into before_data from public.staff_schedule_preferences x where coach_id=p_coach_id;
    insert into public.staff_schedule_preferences(coach_id,base_shift) values(p_coach_id,base)
     on conflict(coach_id) do update set base_shift=excluded.base_shift,updated_at=now();
   else
    select base_shift into base from public.staff_schedule_preferences where coach_id=p_coach_id for share;
    if base is null then raise exception '請先儲存A班或B班預設';end if;
    if p_payload->>'base_shift' is distinct from base then raise exception '預設班別已變更，請重新載入';end if;
    before_data:='[]'::jsonb;
   end if;
   with added as (
    insert into public.staff_schedule_days(coach_id,month_start,work_date,shift_code,start_time,end_time)
    select p_coach_id,p_month,g::date,
      case when extract(isodow from g)=7 then 'regular_off' else base end,
      case when extract(isodow from g)=7 then null when base='A' then time '09:00' else time '12:00' end,
      case when extract(isodow from g)=7 then null when base='A' then time '18:00' else time '21:00' end
    from generate_series(p_month::timestamp,(p_month+interval '1 month'-interval '1 day')::timestamp,interval '1 day') g
    on conflict(coach_id,work_date) do nothing returning *
   ) select coalesce(jsonb_agg(to_jsonb(added)),'[]') into after_data from added;
   if p_action='apply' then after_data:=jsonb_build_object('base_shift',base,'added_days',after_data);end if;
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
grant execute on function schedule_private.command(uuid,uuid,date,integer,text,jsonb) to authenticated;
