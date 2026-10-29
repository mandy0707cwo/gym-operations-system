-- v1.13.37：保留原中止，追加不可變撤銷；本 migration 不執行任何中止或撤銷。
begin;
set local lock_timeout='10s';
set local statement_timeout='45s';
create schema termination_private;
revoke all on schema termination_private from public,anon,authenticated,service_role;
grant usage on schema termination_private to authenticated;

alter table public.course_terminations add column reversed_at timestamptz;
create table public.course_termination_reversals (
 id uuid primary key default gen_random_uuid(),
 termination_id uuid not null unique references public.course_terminations(id),
 purchase_id uuid not null references public.purchases(id),
 operation_id uuid not null,
 reason text not null check(length(trim(reason)) between 1 and 1000),
 settlement_confirmed boolean not null check(settlement_confirmed),
 reversal_date date not null check(isfinite(reversal_date)),
 created_at timestamptz not null,
 created_by uuid not null references public.profiles(id),
 restored_status text not null check(restored_status in ('active','completed')),
 original_termination jsonb not null,
 original_purchase jsonb not null,
 bonus_rule_snapshot jsonb,
 unique(created_by,operation_id),
 check(reversal_date=(created_at at time zone 'Asia/Taipei')::date)
);
create index termination_reversal_purchase_idx on public.course_termination_reversals(purchase_id,reversal_date);
alter table public.course_termination_reversals enable row level security;
revoke all on public.course_termination_reversals from public,anon,authenticated,service_role;
grant select on public.course_termination_reversals to authenticated,service_role;
create policy termination_reversal_admin_read on public.course_termination_reversals for select to authenticated
 using (exists(select 1 from public.profiles p where p.id=(select auth.uid()) and p.active and p.role='admin'));

-- 允許已撤銷的購課日後再中止；同時只能有一筆有效中止。
do $$ declare c record; n integer:=0; begin
 for c in select conname from pg_constraint where conrelid='public.course_terminations'::regclass
   and contype='u' and conkey=array[(select attnum from pg_attribute where attrelid='public.course_terminations'::regclass and attname='purchase_id')] loop
  execute format('alter table public.course_terminations drop constraint %I',c.conname); n:=n+1;
 end loop;
 if n<>1 then raise exception '原中止唯一約束版本不符，停止升級';end if;
end $$;
create unique index one_effective_course_termination on public.course_terminations(purchase_id) where reversed_at is null;

create function termination_private.immutable_reversal() returns trigger
language plpgsql security invoker set search_path='' as $$
begin raise exception '撤銷紀錄不可修改或刪除，須保留追蹤';end $$;
revoke all on function termination_private.immutable_reversal() from public,anon,authenticated,service_role;
create trigger immutable_termination_reversal before update or delete on public.course_termination_reversals
 for each row execute function termination_private.immutable_reversal();

create function termination_private.guard_original() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if tg_op='DELETE' then
  raise exception '中止紀錄不可刪除，請使用撤銷中止';
 elsif tg_op='INSERT' then
  if new.reversed_at is not null then raise exception '新增中止不可預先標記撤銷';end if;
  return new;
 elsif old.reversed_at is not null and to_jsonb(new) is distinct from to_jsonb(old) then
  raise exception '已撤銷中止的原始內容不可修改';
 elsif new.reversed_at is distinct from old.reversed_at then
  if old.reversed_at is not null or new.reversed_at is null
    or (to_jsonb(new)-'reversed_at') is distinct from (to_jsonb(old)-'reversed_at')
    or not exists(select 1 from public.course_termination_reversals r
      where r.termination_id=old.id and r.purchase_id=old.purchase_id and r.created_at=new.reversed_at) then
   raise exception '撤銷標記須由完整撤銷交易建立';
  end if;
 end if;
 return new;
end $$;
revoke all on function termination_private.guard_original() from public,anon,authenticated,service_role;
create trigger guard_termination_original before insert or update or delete on public.course_terminations
 for each row execute function termination_private.guard_original();

-- 舊中止不再阻擋撤銷後的銷課；已撤銷原單的金額永遠保留，不再跟新銷課重算。
do $migration$ declare d text; old_text text; begin
 d:=pg_get_functiondef('finance_private.rebuild_purchase(uuid)'::regprocedure);
 old_text:='for r in select * from public.course_terminations where purchase_id=pid loop';
 if strpos(d,old_text)=0 then raise exception '財務派生函式版本不符';end if;
 execute replace(d,old_text,'for r in select * from public.course_terminations where purchase_id=pid and reversed_at is null loop');
 d:=pg_get_functiondef('public.terminate_course(uuid,date,text,boolean,boolean,uuid,text,text)'::regprocedure);
 old_text:='if exists(select 1 from public.course_terminations where purchase_id=p_purchase_id) then';
 if strpos(d,old_text)=0 then raise exception '課程中止函式版本不符';end if;
 execute replace(d,old_text,'if exists(select 1 from public.course_terminations where purchase_id=p_purchase_id and reversed_at is null) then');
end $migration$;

create function termination_private.reverse_course(p_operation_id uuid,p_termination_id uuid,p_reason text,p_settlement_confirmed boolean)
returns jsonb language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare a uuid:=auth.uid(); t public.course_terminations%rowtype; p public.purchases%rowtype;
 r public.course_termination_reversals%rowtype; pid uuid; role_name text;
 stamp timestamptz:=clock_timestamp(); day date:=(stamp at time zone 'Asia/Taipei')::date;
 restored text; used integer; reason_value text:=btrim(coalesce(p_reason,'')); bonus_snapshot jsonb;
begin
 select role::text into role_name from public.profiles where id=a and active;
 if a is null or role_name is distinct from 'admin' then raise exception using errcode='42501',message='僅有效系統管理員可撤銷中止';end if;
 if p_operation_id is null or p_termination_id is null or length(reason_value) not between 1 and 1000
    or p_settlement_confirmed is distinct from true then raise exception '請填寫撤銷原因並確認款項及獎金處理';end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,37));
 select * into r from public.course_termination_reversals where created_by=a and operation_id=p_operation_id;
 if found then
  if r.termination_id<>p_termination_id or r.reason<>reason_value or r.settlement_confirmed is distinct from p_settlement_confirmed then
   raise exception '操作識別碼內容不同，請查核原操作';end if;
  return jsonb_build_object('id',r.id,'termination_id',r.termination_id,'purchase_id',r.purchase_id,
   'reversal_date',r.reversal_date,'restored_status',r.restored_status);
 end if;
 select purchase_id into pid from public.course_terminations where id=p_termination_id;
 if not found then raise exception '找不到原中止紀錄';end if;
 -- 與中止、銷課及財務派生值鎖同一購課，固定先購課後原中止的順序。
 select * into p from public.purchases where id=pid for update;
 if not found then raise exception '找不到購課紀錄';end if;
 select * into t from public.course_terminations where id=p_termination_id for update;
 if t.reversed_at is not null or exists(select 1 from public.course_termination_reversals where termination_id=t.id) then
  raise exception '這筆中止已撤銷，不可重複沖回';end if;
 if t.termination_date>day then raise exception '原中止日期晚於今日，請先查核，不可產生早於原中止的撤銷';end if;
 if p.status is distinct from (case when t.termination_type='expired' then 'expired' else 'cancelled' end) then
  raise exception '課程狀態與原中止不符，停止撤銷，請先查核';end if;
 select count(*) into used from public.session_usages where purchase_id=pid;
 restored:=case when used>=p.total_sessions then 'completed' else 'active' end;
 select to_jsonb(b) into bonus_snapshot from public.bonus_rules b where b.active
  and b.effective_from<=t.termination_date and (b.effective_to is null or b.effective_to>=t.termination_date)
  order by b.effective_from desc limit 1;
 insert into public.course_termination_reversals(termination_id,purchase_id,operation_id,reason,settlement_confirmed,
   reversal_date,created_at,created_by,restored_status,original_termination,original_purchase,bonus_rule_snapshot)
 values(t.id,pid,p_operation_id,reason_value,true,day,stamp,a,restored,to_jsonb(t),to_jsonb(p),bonus_snapshot) returning * into r;
 update public.course_terminations set reversed_at=stamp where id=t.id;
 update public.purchases set status=restored where id=pid;
 return jsonb_build_object('id',r.id,'termination_id',t.id,'purchase_id',pid,'reversal_date',day,'restored_status',restored);
end $$;
revoke all on function termination_private.reverse_course(uuid,uuid,text,boolean) from public,anon,authenticated,service_role;
grant execute on function termination_private.reverse_course(uuid,uuid,text,boolean) to authenticated;
create function public.reverse_course_termination(p_operation_id uuid,p_termination_id uuid,p_reason text,p_settlement_confirmed boolean)
returns jsonb language sql security invoker set search_path='' as $$
 select termination_private.reverse_course(p_operation_id,p_termination_id,p_reason,p_settlement_confirmed);
$$;
revoke all on function public.reverse_course_termination(uuid,uuid,text,boolean) from public,anon,authenticated,service_role;
grant execute on function public.reverse_course_termination(uuid,uuid,text,boolean) to authenticated;

-- 防止恢復後把銷課倒填到原本有效中止的期間；不延長效期、不改已銷課堂次。
create function termination_private.guard_usage_interval() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.course_terminations t where t.purchase_id=new.purchase_id
   and new.usage_date>=t.termination_date and (t.reversed_at is null or
    new.usage_date<(t.reversed_at at time zone 'Asia/Taipei')::date)) then
  raise exception '銷課日期落在有效中止期間，請先查核日期';end if;
 return new;
end $$;
revoke all on function termination_private.guard_usage_interval() from public,anon,authenticated,service_role;
create trigger termination_usage_interval before insert or update of purchase_id,usage_date on public.session_usages
 for each row execute function termination_private.guard_usage_interval();

-- 原金額留在原月份，精確負數沖回留在撤銷月份；不能以今天已撤銷就刪掉以前月份。
create view public.course_termination_events with (security_invoker=true) as
 select t.id,t.purchase_id,t.termination_date,t.termination_type,t.remaining_sessions,t.remaining_amount,
 t.charge_fee,t.fee_rate,t.fee_amount,t.refund_amount,t.recognized_amount,t.completion_bonus_eligible,
 t.completion_bonus_coach_id,t.reason,t.note,t.created_at,t.created_by,t.remaining_net_amount,
 t.recognized_net_amount,t.fee_net_amount,t.refund_net_amount,t.calculation_rule_version,
 false as is_reversal,t.termination_date as original_termination_date,t.id as original_termination_id,
 r.original_purchase as purchase_snapshot,r.bonus_rule_snapshot,(r.id is not null) as snapshot_available
 from public.course_terminations t left join public.course_termination_reversals r on r.termination_id=t.id
 union all
 select r.id,t.purchase_id,r.reversal_date,t.termination_type,-t.remaining_sessions,-t.remaining_amount,
 t.charge_fee,t.fee_rate,-t.fee_amount,-t.refund_amount,-t.recognized_amount,t.completion_bonus_eligible,
 t.completion_bonus_coach_id,r.reason,t.note,r.created_at,r.created_by,-t.remaining_net_amount,
 -t.recognized_net_amount,-t.fee_net_amount,-t.refund_net_amount,t.calculation_rule_version,
 true,t.termination_date,t.id,r.original_purchase,r.bonus_rule_snapshot,true
 from public.course_termination_reversals r join public.course_terminations t on t.id=r.termination_id;
revoke all on public.course_termination_events from public,anon,authenticated,service_role;
grant select on public.course_termination_events to authenticated,service_role;
commit;
