-- 專案儲值扣款與事後請款（保留既有專案資料）
alter table public.project_entries
  add column if not exists member_id uuid references public.members(id),
  add column if not exists payment_method text not null default 'postpaid'
    check (payment_method in ('wallet','postpaid')),
  add column if not exists billing_status text not null default 'unbilled'
    check (billing_status in ('unbilled','billed','partial','paid','cancelled')),
  add column if not exists received_amount numeric(12,2) not null default 0
    check (received_amount >= 0),
  add column if not exists billed_date date,
  add column if not exists note text,
  add column if not exists total_amount numeric(12,2);
update public.project_entries
set total_amount=round(quantity*unit_price,2)
where total_amount is null;
alter table public.project_entries alter column total_amount set not null;
alter table public.project_entries alter column total_amount set default 0;
alter table public.project_entries drop constraint if exists project_entries_total_amount_check;
alter table public.project_entries add constraint project_entries_total_amount_check check (total_amount >= 0);

create table if not exists public.project_wallet_transactions (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references public.members(id),
  transaction_date date not null,
  transaction_type text not null check (transaction_type in ('topup','deduction','reversal','adjustment')),
  amount numeric(12,2) not null check (amount <> 0),
  project_entry_id uuid references public.project_entries(id),
  note text,
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  check (
    (transaction_type='topup' and amount > 0) or
    (transaction_type='deduction' and amount < 0) or
    (transaction_type in ('reversal','adjustment'))
  )
);

create table if not exists public.project_members (
  member_id uuid primary key references public.members(id),
  allow_wallet boolean not null default false,
  allow_postpaid boolean not null default false,
  active boolean not null default true,
  note text,
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (allow_wallet or allow_postpaid)
);

-- 已由管理員建立過儲值的會員，沿用為可使用專案儲值的會員。
insert into public.project_members(member_id,allow_wallet,allow_postpaid,created_by)
select distinct t.member_id,true,false,t.created_by
from public.project_wallet_transactions t
where t.transaction_type='topup' and t.amount>0
on conflict(member_id) do update set allow_wallet=true,active=true,updated_at=now();

create table if not exists public.project_receipt_transactions (
  id uuid primary key default gen_random_uuid(),
  project_entry_id uuid not null references public.project_entries(id),
  receipt_date date not null,
  amount numeric(12,2) not null check (amount > 0),
  note text,
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now()
);

create index if not exists idx_project_entries_member on public.project_entries(member_id);
create index if not exists idx_project_entries_billing on public.project_entries(payment_method,billing_status,entry_date desc);
create index if not exists idx_project_wallet_member_date on public.project_wallet_transactions(member_id,transaction_date desc);
create index if not exists idx_project_receipt_entry_date on public.project_receipt_transactions(project_entry_id,receipt_date desc);

create or replace view public.project_wallet_balances with (security_invoker=true) as
select m.id member_id, m.member_name,
       coalesce(sum(t.amount),0)::numeric(12,2) balance
from public.members m
left join public.project_wallet_transactions t on t.member_id=m.id
group by m.id,m.member_name;

drop function if exists public.get_project_wallet_members();
-- 專案登錄只取得由系統管理員核准的專案會員與付款方式，不公開交易金額。
create or replace function public.get_project_members()
returns table(member_id uuid,member_name text,allow_wallet boolean,allow_postpaid boolean)
language sql stable security definer set search_path=public as $$
  select m.id,m.member_name,pm.allow_wallet,pm.allow_postpaid
  from public.project_members pm
  join public.members m on m.id=pm.member_id
  where m.active and pm.active
    and exists (select 1 from public.profiles p where p.id=auth.uid() and p.active)
  order by m.member_name;
$$;

create or replace function public.create_project_member(
  p_member_name text, p_allow_wallet boolean, p_allow_postpaid boolean, p_note text default null
) returns public.project_members
language plpgsql security definer set search_path=public as $$
declare
  v_member_id uuid;
  v_row public.project_members%rowtype;
begin
  if not public.is_admin() then raise exception '僅系統管理員可建立專案會員'; end if;
  if nullif(trim(p_member_name),'') is null then raise exception '會員姓名不可空白'; end if;
  if not p_allow_wallet and not p_allow_postpaid then raise exception '至少選擇一種付款方式'; end if;

  select id into v_member_id from public.members where member_name=trim(p_member_name);
  if v_member_id is null then
    insert into public.members(member_name,active,created_by)
    values(trim(p_member_name),true,auth.uid()) returning id into v_member_id;
  else
    update public.members set active=true where id=v_member_id;
  end if;

  insert into public.project_members(member_id,allow_wallet,allow_postpaid,active,note,created_by,updated_at)
  values(v_member_id,p_allow_wallet,p_allow_postpaid,true,nullif(trim(p_note),''),auth.uid(),now())
  on conflict(member_id) do update set
    allow_wallet=excluded.allow_wallet,allow_postpaid=excluded.allow_postpaid,
    active=true,note=excluded.note,updated_at=now()
  returning * into v_row;
  return v_row;
end; $$;

create or replace function public.create_project_entry(
  p_entry_date date, p_catalog_id uuid, p_member_id uuid, p_person_name text,
  p_coach_id uuid, p_quantity numeric, p_total_amount numeric,
  p_payment_method text, p_note text default null
) returns public.project_entries
language plpgsql security definer set search_path=public as $$
declare
  v_catalog public.project_catalog%rowtype;
  v_balance numeric(12,2);
  v_entry public.project_entries%rowtype;
begin
  if auth.uid() is null then raise exception '尚未登入'; end if;
  if not exists (
    select 1 from public.profiles
    where id=auth.uid() and active and
      (id=p_coach_id or role in ('shared_coach','manager','admin'))
  ) then raise exception '沒有權限替此教練建立專案紀錄'; end if;
  if p_payment_method not in ('wallet','postpaid') then raise exception '付款方式不正確'; end if;
  if p_quantity <= 0 then raise exception '數量必須大於零'; end if;
  if p_total_amount < 0 then raise exception '金額不可小於零'; end if;
  if p_member_id is null then raise exception '請選擇會員'; end if;
  select * into v_catalog from public.project_catalog where id=p_catalog_id;
  if not found then raise exception '找不到專案項目'; end if;

  -- 同一會員的儲值操作使用交易鎖，避免同時扣款造成負餘額。
  perform pg_advisory_xact_lock(hashtextextended(p_member_id::text,0));
  if p_payment_method='wallet' then
    if not exists (select 1 from public.project_members where member_id=p_member_id and active and allow_wallet)
      then raise exception '此會員未取得專案儲值資格，請由系統管理員新增'; end if;
    select coalesce(sum(amount),0) into v_balance
    from public.project_wallet_transactions where member_id=p_member_id;
    if v_balance < p_total_amount then raise exception '儲值餘額不足，目前餘額：%',v_balance; end if;
  elsif not exists (select 1 from public.project_members where member_id=p_member_id and active and allow_postpaid) then
    raise exception '此會員未取得專案事後請款資格，請由系統管理員新增';
  end if;

  insert into public.project_entries(
    entry_date,project_catalog_id,project_name,member_id,person_name,coach_id,
    item_name,item_hours,quantity,unit_price,total_amount,payment_method,billing_status,
    received_amount,note,created_by
  ) values (
    p_entry_date,v_catalog.id,v_catalog.project_name,p_member_id,trim(p_person_name),p_coach_id,
    v_catalog.item_name,v_catalog.hours,p_quantity,
    case when p_quantity=0 then 0 else round(p_total_amount/p_quantity,2) end,p_total_amount,
    p_payment_method,case when p_payment_method='wallet' then 'paid' else 'unbilled' end,
    case when p_payment_method='wallet' then p_total_amount else 0 end,
    nullif(trim(p_note),''),auth.uid()
  ) returning * into v_entry;

  if p_payment_method='wallet' and p_total_amount > 0 then
    insert into public.project_wallet_transactions(
      member_id,transaction_date,transaction_type,amount,project_entry_id,note,created_by
    ) values (p_member_id,p_entry_date,'deduction',-p_total_amount,v_entry.id,
              '專案扣款：'||v_catalog.project_name||'／'||v_catalog.item_name,auth.uid());
  end if;
  return v_entry;
end; $$;

create or replace function public.record_project_receipt(
  p_project_entry_id uuid, p_receipt_date date, p_amount numeric, p_note text default null
) returns public.project_entries
language plpgsql security definer set search_path=public as $$
declare
  v_entry public.project_entries%rowtype;
  v_total numeric(12,2);
begin
  if not public.is_admin() then raise exception '僅系統管理員可登錄專案收款'; end if;
  select * into v_entry from public.project_entries where id=p_project_entry_id for update;
  if not found then raise exception '找不到專案紀錄'; end if;
  if v_entry.payment_method <> 'postpaid' then raise exception '儲值扣款紀錄不可登錄事後收款'; end if;
  if v_entry.billing_status='cancelled' then raise exception '已取消紀錄不可收款'; end if;
  if p_amount <= 0 then raise exception '收款金額必須大於零'; end if;
  v_total := v_entry.total_amount;
  if v_entry.received_amount+p_amount > v_total then raise exception '收款金額超過未收金額'; end if;
  insert into public.project_receipt_transactions(project_entry_id,receipt_date,amount,note,created_by)
  values (p_project_entry_id,p_receipt_date,p_amount,nullif(trim(p_note),''),auth.uid());
  update public.project_entries
  set received_amount=received_amount+p_amount,
      billed_date=coalesce(billed_date,p_receipt_date),
      billing_status=case when received_amount+p_amount>=v_total then 'paid' else 'partial' end
  where id=p_project_entry_id returning * into v_entry;
  return v_entry;
end; $$;

create or replace function public.protect_project_financial_history()
returns trigger language plpgsql set search_path=public as $$
begin
  if tg_op='DELETE' then
    if old.payment_method='wallet' or exists(select 1 from public.project_receipt_transactions where project_entry_id=old.id) then
      raise exception '此專案已有財務交易，不可直接刪除；請使用沖銷功能';
    end if;
    return old;
  end if;
  if old.payment_method='wallet' then
    raise exception '儲值扣款紀錄不可直接修改；請使用沖銷功能';
  end if;
  if new.total_amount < old.received_amount then
    raise exception '修改後總額不可小於已收金額';
  end if;
  return new;
end; $$;
drop trigger if exists protect_project_financial_history on public.project_entries;
create trigger protect_project_financial_history
before update or delete on public.project_entries
for each row execute function public.protect_project_financial_history();

alter table public.project_wallet_transactions enable row level security;
alter table public.project_members enable row level security;
alter table public.project_receipt_transactions enable row level security;
drop policy if exists project_wallet_read on public.project_wallet_transactions;
drop policy if exists project_wallet_admin_insert on public.project_wallet_transactions;
create policy project_wallet_read on public.project_wallet_transactions
  for select to authenticated using (public.is_manager());
create policy project_wallet_admin_insert on public.project_wallet_transactions
  for insert to authenticated with check (public.is_admin() and created_by=auth.uid());
drop policy if exists project_members_admin_all on public.project_members;
create policy project_members_admin_all on public.project_members
  for all to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists project_receipt_read on public.project_receipt_transactions;
drop policy if exists project_receipt_admin_insert on public.project_receipt_transactions;
create policy project_receipt_read on public.project_receipt_transactions
  for select to authenticated using (public.is_manager());
create policy project_receipt_admin_insert on public.project_receipt_transactions
  for insert to authenticated with check (public.is_admin() and created_by=auth.uid());

grant select on public.project_wallet_balances to authenticated;
revoke all on function public.get_project_members() from public;
revoke all on function public.create_project_member(text,boolean,boolean,text) from public;
revoke all on function public.create_project_entry(date,uuid,uuid,text,uuid,numeric,numeric,text,text) from public;
revoke all on function public.record_project_receipt(uuid,date,numeric,text) from public;
grant execute on function public.create_project_entry(date,uuid,uuid,text,uuid,numeric,numeric,text,text) to authenticated;
grant execute on function public.record_project_receipt(uuid,date,numeric,text) to authenticated;
grant execute on function public.get_project_members() to authenticated;
grant execute on function public.create_project_member(text,boolean,boolean,text) to authenticated;
