-- v1.11.0 課程逾期／退費中止
-- 中止金額採資料庫鎖定後計算，不建立銷課紀錄，因此不影響執行時數。

create table if not exists public.course_terminations (
  id uuid primary key default gen_random_uuid(),
  purchase_id uuid not null unique references public.purchases(id),
  termination_date date not null,
  termination_type text not null check (termination_type in ('expired','refund')),
  remaining_sessions integer not null check (remaining_sessions >= 0),
  remaining_amount numeric(12,2) not null check (remaining_amount >= 0),
  charge_fee boolean not null default false,
  fee_rate numeric(6,5) not null default 0 check (fee_rate between 0 and 1),
  fee_amount numeric(12,2) not null default 0 check (fee_amount >= 0),
  refund_amount numeric(12,2) not null default 0 check (refund_amount >= 0),
  recognized_amount numeric(12,2) not null default 0 check (recognized_amount >= 0),
  completion_bonus_eligible boolean not null default false,
  completion_bonus_coach_id uuid references public.profiles(id),
  reason text,
  note text,
  created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id),
  check (
    (termination_type='expired' and not charge_fee and fee_rate=0 and fee_amount=0 and refund_amount=0)
    or
    (termination_type='refund' and not completion_bonus_eligible and completion_bonus_coach_id is null)
  ),
  check (not completion_bonus_eligible or completion_bonus_coach_id is not null)
);

create index if not exists idx_course_terminations_date
  on public.course_terminations(termination_date desc);
create index if not exists idx_course_terminations_bonus_coach
  on public.course_terminations(completion_bonus_coach_id, termination_date)
  where completion_bonus_eligible;

alter table public.course_terminations enable row level security;

drop policy if exists course_terminations_admin_read on public.course_terminations;
create policy course_terminations_admin_read
on public.course_terminations for select to authenticated
using ((select public.is_admin()));

drop policy if exists course_terminations_admin_insert on public.course_terminations;
create policy course_terminations_admin_insert
on public.course_terminations for insert to authenticated
with check ((select public.is_admin()) and created_by=(select auth.uid()));

create or replace function public.terminate_course(
  p_purchase_id uuid,
  p_termination_date date,
  p_termination_type text,
  p_charge_fee boolean default false,
  p_completion_bonus_eligible boolean default false,
  p_completion_bonus_coach_id uuid default null,
  p_reason text default null,
  p_note text default null
) returns public.course_terminations
language plpgsql security invoker set search_path=public as $$
declare
  v_purchase public.purchases%rowtype;
  v_used_sessions integer;
  v_used_amount numeric(12,2);
  v_remaining_sessions integer;
  v_remaining_amount numeric(12,2);
  v_fee_rate numeric(6,5);
  v_fee_amount numeric(12,2);
  v_refund_amount numeric(12,2);
  v_recognized_amount numeric(12,2);
  v_row public.course_terminations%rowtype;
begin
  if not (select public.is_admin()) then
    raise exception '僅限系統管理員執行課程中止';
  end if;
  if p_termination_type not in ('expired','refund') then
    raise exception '中止類型必須為逾期或退費';
  end if;

  select * into v_purchase from public.purchases
  where id=p_purchase_id for update;
  if not found then raise exception '找不到購買紀錄'; end if;
  if v_purchase.status <> 'active' then raise exception '此課程不是有效狀態'; end if;
  if exists(select 1 from public.course_terminations where purchase_id=p_purchase_id) then
    raise exception '此課程已有中止紀錄';
  end if;

  select count(*)::integer, coalesce(sum(deducted_amount),0)
  into v_used_sessions, v_used_amount
  from public.session_usages where purchase_id=p_purchase_id;

  v_remaining_sessions := greatest(v_purchase.total_sessions-v_used_sessions,0);
  v_remaining_amount := greatest(round(v_purchase.total_amount-v_used_amount,2),0);
  if v_remaining_sessions=0 then raise exception '此課程已完成，無法中止'; end if;

  if p_termination_type='refund' then
    v_fee_rate := case when p_charge_fee then 0.20 else 0 end;
    v_fee_amount := round(v_remaining_amount*v_fee_rate,2);
    v_refund_amount := greatest(v_remaining_amount-v_fee_amount,0);
    v_recognized_amount := v_fee_amount;
    p_completion_bonus_eligible := false;
    p_completion_bonus_coach_id := null;
  else
    v_fee_rate := 0;
    v_fee_amount := 0;
    v_refund_amount := 0;
    v_recognized_amount := v_remaining_amount;
    if p_completion_bonus_eligible and p_completion_bonus_coach_id is null then
      raise exception '計算結單獎金時必須指定歸屬教練';
    end if;
    if not p_completion_bonus_eligible then p_completion_bonus_coach_id := null; end if;
  end if;

  insert into public.course_terminations(
    purchase_id,termination_date,termination_type,remaining_sessions,remaining_amount,
    charge_fee,fee_rate,fee_amount,refund_amount,recognized_amount,
    completion_bonus_eligible,completion_bonus_coach_id,reason,note,created_by
  ) values (
    p_purchase_id,p_termination_date,p_termination_type,v_remaining_sessions,v_remaining_amount,
    p_termination_type='refund' and p_charge_fee,v_fee_rate,v_fee_amount,v_refund_amount,v_recognized_amount,
    p_termination_type='expired' and p_completion_bonus_eligible,p_completion_bonus_coach_id,
    nullif(trim(p_reason),''),nullif(trim(p_note),''),auth.uid()
  ) returning * into v_row;

  update public.purchases
  set status=case when p_termination_type='expired' then 'expired' else 'cancelled' end
  where id=p_purchase_id;

  return v_row;
end; $$;

revoke all on function public.terminate_course(uuid,date,text,boolean,boolean,uuid,text,text) from public;
grant execute on function public.terminate_course(uuid,date,text,boolean,boolean,uuid,text,text) to authenticated;
grant select on public.course_terminations to authenticated;


