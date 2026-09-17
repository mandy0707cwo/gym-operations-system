begin;

-- 銷課未稅金額是會計入帳值，建立後固定保存，不在報表查詢時逐筆重新換算。
alter table public.session_usages
  add column if not exists deducted_net_amount numeric(12,2);

-- 既有資料依同一購買課程的堂次順序進行累計差額分攤。
-- 每筆未稅 = 本筆後累計含稅換算值 - 本筆前累計含稅換算值。
with allocated as (
  select
    id,
    round(
      sum(deducted_amount) over (
        partition by purchase_id
        order by session_seq,usage_date,created_at,id
        rows between unbounded preceding and current row
      ) / 1.05,
      0
    ) - round(
      (
        sum(deducted_amount) over (
          partition by purchase_id
          order by session_seq,usage_date,created_at,id
          rows between unbounded preceding and current row
        ) - deducted_amount
      ) / 1.05,
      0
    ) as deducted_net_amount
  from public.session_usages
)
update public.session_usages usage
set deducted_net_amount=allocated.deducted_net_amount
from allocated
where usage.id=allocated.id
  and usage.deducted_net_amount is null;

alter table public.session_usages
  alter column deducted_net_amount set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname='session_usages_deducted_net_amount_check'
      and conrelid='public.session_usages'::regclass
  ) then
    alter table public.session_usages
      add constraint session_usages_deducted_net_amount_check
      check (deducted_net_amount >= 0);
  end if;
end $$;

create or replace function public.consume_session(
  p_purchase_id uuid,
  p_usage_date date,
  p_coach_id uuid,
  p_note text default null,
  p_is_makeup boolean default false,
  p_actual_usage_date date default null
) returns public.session_usages
language plpgsql security invoker set search_path=public as $$
declare
  v_purchase public.purchases%rowtype;
  v_used integer;
  v_next_seq integer;
  v_deducted numeric(12,2);
  v_deducted_net numeric(12,2);
  v_prior_gross numeric(12,2);
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

  if v_used + 1 = v_purchase.total_sessions then
    select round(v_purchase.total_amount-coalesce(sum(deducted_amount),0),2)
      into v_deducted
    from public.session_usages
    where purchase_id=p_purchase_id;
  else
    v_deducted := round(v_purchase.total_amount/v_purchase.total_sessions,2);
  end if;

  select coalesce(sum(deducted_amount),0),coalesce(sum(deducted_net_amount),0)
    into v_prior_gross,v_prior_net
  from public.session_usages
  where purchase_id=p_purchase_id;

  -- 累計分攤可保證：全部未稅明細合計 = round(全部含稅合計 / 1.05)。
  v_deducted_net := round((v_prior_gross+v_deducted)/1.05,0)-v_prior_net;

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
end; $$;

revoke all on function public.consume_session(uuid,date,uuid,text,boolean,date) from public;
grant execute on function public.consume_session(uuid,date,uuid,text,boolean,date) to authenticated;

commit;

-- 執行後驗證：此查詢應回傳 0 筆。
select purchase_id,
       round(sum(deducted_amount)/1.05,0) expected_net_amount,
       sum(deducted_net_amount) stored_net_amount
from public.session_usages
group by purchase_id
having round(sum(deducted_amount)/1.05,0) <> sum(deducted_net_amount);
