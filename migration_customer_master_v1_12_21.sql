-- v1.12.21：沿用 members 建立客戶主檔、歷史資料回填與修改稽核。
-- 可重複執行；不重建 member_id，也不修改購課、付款、銷課及課程中止的既有關聯。

alter table public.members add column if not exists gender text;
alter table public.members add column if not exists birth_date date;
alter table public.members add column if not exists phone text;
alter table public.members add column if not exists contact_method text;
alter table public.members add column if not exists customer_source text;
alter table public.members add column if not exists referral text;
alter table public.members add column if not exists responsible_coach_id uuid references public.profiles(id);
alter table public.members add column if not exists initial_contact_date date;
alter table public.members add column if not exists customer_status text not null default 'prospect';
alter table public.members add column if not exists emergency_contact text;
alter table public.members add column if not exists emergency_phone text;
alter table public.members add column if not exists note text;
alter table public.members add column if not exists updated_at timestamptz not null default now();
alter table public.members add column if not exists updated_by uuid references public.profiles(id);

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid='public.members'::regclass
      and conname='members_customer_status_check'
  ) then
    alter table public.members add constraint members_customer_status_check
      check (customer_status in ('prospect','trial','member','paused','ended')) not valid;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid='public.members'::regclass
      and conname='members_gender_check'
  ) then
    alter table public.members add constraint members_gender_check
      check (gender is null or gender in ('女','男','其他')) not valid;
  end if;
end $$;

alter table public.members validate constraint members_customer_status_check;
alter table public.members validate constraint members_gender_check;

-- 已購課客戶沿用原 member_id，自動補入正式會員狀態、最早接觸日期及最近一次成交教練。
update public.members m
set customer_status='member',
    initial_contact_date=coalesce(m.initial_contact_date,p.first_purchase_date),
    responsible_coach_id=coalesce(m.responsible_coach_id,p.latest_coach_id),
    updated_at=now()
from (
  select member_id,min(purchase_date) first_purchase_date,
    (array_agg(coach_id order by purchase_date desc,created_at desc,id desc))[1] latest_coach_id
  from public.purchases
  group by member_id
) p
where p.member_id=m.id
  and (m.customer_status='prospect' or m.initial_contact_date is null or m.responsible_coach_id is null);

create table if not exists public.member_change_logs (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references public.members(id) on delete restrict,
  changed_by uuid references public.profiles(id),
  changed_at timestamptz not null default now(),
  old_data jsonb not null,
  new_data jsonb not null
);

create index if not exists idx_members_customer_status on public.members(customer_status,active);
create index if not exists idx_members_responsible_coach on public.members(responsible_coach_id);
create index if not exists idx_member_change_logs_member_time on public.member_change_logs(member_id,changed_at desc);

create or replace function public.audit_member_change()
returns trigger
language plpgsql
security definer
set search_path=pg_catalog,public
as $$
begin
  new.updated_at=now();
  if auth.uid() is not null then
    new.updated_by=auth.uid();
  end if;
  if to_jsonb(new) is distinct from to_jsonb(old) then
    insert into public.member_change_logs(member_id,changed_by,old_data,new_data)
    values(new.id,new.updated_by,to_jsonb(old),to_jsonb(new));
  end if;
  return new;
end;
$$;

revoke all on function public.audit_member_change() from public,anon,authenticated;

drop trigger if exists members_audit_update on public.members;
create trigger members_audit_update
before update on public.members
for each row execute function public.audit_member_change();

alter table public.member_change_logs enable row level security;
drop policy if exists member_change_logs_admin_read on public.member_change_logs;
create policy member_change_logs_admin_read on public.member_change_logs
for select to authenticated using (public.is_admin());

-- 教練只讀取自己建立、負責或已有自己購課紀錄的客戶；共用教練、主管與管理員維持全部可讀。
drop policy if exists members_read on public.members;
create policy members_read on public.members
for select to authenticated
using (
  (select public.is_manager())
  or created_by=(select auth.uid())
  or responsible_coach_id=(select auth.uid())
  or exists (
    select 1 from public.purchases p
    where p.member_id=members.id and p.coach_id=(select auth.uid())
  )
);

drop policy if exists members_update on public.members;
create policy members_update on public.members
for update to authenticated
using (
  (select public.is_manager())
  or created_by=(select auth.uid())
  or responsible_coach_id=(select auth.uid())
  or exists (
    select 1 from public.purchases p
    where p.member_id=members.id and p.coach_id=(select auth.uid())
  )
)
with check (
  (select public.is_manager())
  or created_by=(select auth.uid())
  or responsible_coach_id=(select auth.uid())
  or exists (
    select 1 from public.purchases p
    where p.member_id=members.id and p.coach_id=(select auth.uid())
  )
);

grant select,insert on public.member_change_logs to authenticated;
grant all on public.member_change_logs to service_role;

select 'v1.12.21 客戶主檔與修改紀錄建立完成' as result;
