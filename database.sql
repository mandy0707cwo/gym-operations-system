-- 健身房營運系統：請在全新的 Supabase 專案之 SQL Editor 一次執行。
create extension if not exists pgcrypto;

create type public.app_role as enum ('coach', 'shared_coach', 'manager', 'admin');
create type public.purchase_kind as enum ('first', 'renewal');
create type public.payment_plan as enum ('full', 'installment');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text unique check (username is null or username ~ '^[a-z0-9_]{3,30}$'),
  display_name text not null check (length(trim(display_name)) > 0),
  role public.app_role not null default 'coach',
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.members (
  id uuid primary key default gen_random_uuid(),
  member_name text not null check (length(trim(member_name)) > 0),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id),
  unique (member_name)
);

create table public.course_catalog (
  id uuid primary key default gen_random_uuid(),
  course_name text not null unique check (length(trim(course_name)) > 0),
  course_type text not null default '未分類' check (length(trim(course_type)) > 0),
  session_hours numeric(4,2) not null default 1 check (session_hours > 0),
  created_at timestamptz not null default now()
);

create table public.operation_item_catalog (
  id uuid primary key default gen_random_uuid(),
  item_type text not null check (item_type in ('trial','single_sale')),
  item_name text not null check (length(trim(item_name)) > 0),
  course_type text,
  session_hours numeric(5,2) not null default 1 check (session_hours > 0),
  created_at timestamptz not null default now(),
  unique (item_type, item_name)
);

create table public.daily_operations (
  id uuid primary key default gen_random_uuid(),
  operation_date date not null,
  coach_id uuid not null references public.profiles(id),
  classes_held integer not null default 0 check (classes_held >= 0),
  classes_cancelled integer not null default 0 check (classes_cancelled >= 0),
  trial_visits integer not null default 0 check (trial_visits >= 0),
  trial_conversions integer not null default 0 check (trial_conversions >= 0),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (operation_date, coach_id),
  check (trial_conversions <= trial_visits)
);

create table public.trial_items (
  id uuid primary key default gen_random_uuid(), entry_date date not null,
  member_name text not null check (length(trim(member_name)) > 0),
  content text not null check (length(trim(content)) > 0),
  course_type text,
  hours numeric(5,2) not null check (hours > 0),
  note text,
  coach_id uuid not null references public.profiles(id),
  created_at timestamptz not null default now(), created_by uuid not null references public.profiles(id)
);

create table public.single_sales (
  id uuid primary key default gen_random_uuid(), entry_date date not null,
  member_name text not null check (length(trim(member_name)) > 0),
  content text not null check (length(trim(content)) > 0),
  course_type text,
  hours numeric(5,2) not null check (hours > 0),
  note text,
  coach_id uuid not null references public.profiles(id),
  created_at timestamptz not null default now(), created_by uuid not null references public.profiles(id)
);

create table public.event_supports (
  id uuid primary key default gen_random_uuid(), entry_date date not null,
  content text not null check (length(trim(content)) > 0),
  hours numeric(5,2) not null check (hours > 0),
  deducted_hours numeric(5,2) not null default 0 check (deducted_hours >= 0 and deducted_hours <= hours),
  deduction_reason text, coach_id uuid not null references public.profiles(id),
  created_at timestamptz not null default now(), created_by uuid not null references public.profiles(id),
  check (deducted_hours = 0 or length(trim(deduction_reason)) > 0)
);

create table public.session_cancellations (
  id uuid primary key default gen_random_uuid(), cancel_date date not null,
  coach_id uuid not null references public.profiles(id),
  cancelled_sessions integer not null check (cancelled_sessions >= 0), reason text,
  created_at timestamptz not null default now(), created_by uuid not null references public.profiles(id)
);

create table public.purchases (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references public.members(id),
  purchase_kind public.purchase_kind not null,
  coach_id uuid not null references public.profiles(id),
  course_name text not null check (length(trim(course_name)) > 0),
  total_sessions integer not null check (total_sessions > 0),
  session_hours numeric(4,2) not null default 1 check (session_hours > 0),
  total_amount numeric(12,2) not null check (total_amount >= 0),
  purchase_date date not null,
  expiry_date date not null,
  payment_plan public.payment_plan not null,
  installment_count smallint not null check (installment_count between 1 and 3),
  referral text,
  note text,
  status text not null default 'active' check (status in ('active','completed','expired','cancelled')),
  created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id),
  check (expiry_date >= purchase_date),
  check ((payment_plan = 'full' and installment_count = 1) or payment_plan = 'installment')
);

create table public.purchase_payments (
  id uuid primary key default gen_random_uuid(),
  purchase_id uuid not null references public.purchases(id) on delete cascade,
  installment_no smallint not null check (installment_no between 1 and 3),
  amount numeric(12,2) not null check (amount > 0),
  paid_date date not null,
  created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id),
  unique (purchase_id, installment_no)
);

create or replace function public.validate_purchase_payment()
returns trigger language plpgsql set search_path=public as $$
declare v_purchase public.purchases%rowtype; v_paid numeric(12,2);
begin
  select * into v_purchase from public.purchases where id=new.purchase_id for update;
  select coalesce(sum(amount),0) into v_paid from public.purchase_payments
    where purchase_id=new.purchase_id and id<>new.id;
  if v_paid + new.amount > v_purchase.total_amount then
    raise exception '累計付款金額不可超過成交總金額';
  end if;
  return new;
end; $$;
create trigger check_purchase_payment before insert or update on public.purchase_payments
for each row execute function public.validate_purchase_payment();

create table public.session_usages (
  id uuid primary key default gen_random_uuid(),
  purchase_id uuid not null references public.purchases(id),
  usage_date date not null,
  coach_id uuid not null references public.profiles(id),
  session_seq integer not null check (session_seq > 0),
  deducted_amount numeric(12,2) not null check (deducted_amount >= 0),
  note text,
  created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id),
  unique (purchase_id, session_seq)
);

create index idx_daily_date_coach on public.daily_operations(operation_date, coach_id);
create index idx_purchase_member on public.purchases(member_id);
create index idx_purchase_date_coach on public.purchases(purchase_date, coach_id);
create index idx_usage_date_coach on public.session_usages(usage_date, coach_id);
create index idx_trial_date_coach on public.trial_items(entry_date, coach_id);
create index idx_single_sale_date_coach on public.single_sales(entry_date, coach_id);
create index idx_event_date_coach on public.event_supports(entry_date, coach_id);
create index idx_cancel_date_coach on public.session_cancellations(cancel_date, coach_id);

create or replace function public.is_manager()
returns boolean language sql stable security definer set search_path = public
as $$ select exists(select 1 from public.profiles where id = auth.uid() and role in ('shared_coach','manager','admin') and active); $$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public
as $$ select exists(select 1 from public.profiles where id = auth.uid() and role = 'admin' and active); $$;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  insert into public.profiles(id, username, display_name, role)
  values(new.id, nullif(lower(trim(new.raw_user_meta_data->>'username')),''),
    coalesce(nullif(trim(new.raw_user_meta_data->>'display_name'),''), split_part(new.email,'@',1)), 'coach');
  return new;
end; $$;
create trigger on_auth_user_created after insert on auth.users
for each row execute procedure public.handle_new_user();

create or replace view public.purchase_balances with (security_invoker=true) as
select p.id purchase_id, p.member_id, m.member_name, p.course_name, p.coach_id,
       pr.display_name coach_name, p.total_sessions, p.total_amount,
       count(u.id)::integer used_sessions,
       p.total_sessions-count(u.id)::integer remaining_sessions,
       round(p.total_amount-coalesce(sum(u.deducted_amount),0),2) remaining_amount,
       p.expiry_date, p.status, p.note, p.referral
from public.purchases p
join public.members m on m.id=p.member_id
join public.profiles pr on pr.id=p.coach_id
left join public.session_usages u on u.purchase_id=p.id
group by p.id,m.member_name,pr.display_name;

-- 原子扣課：鎖定購買資料，最後一堂扣完剩餘金額，避免四捨五入與多人競爭問題。
create or replace function public.consume_session(
  p_purchase_id uuid, p_usage_date date, p_coach_id uuid, p_note text default null
) returns public.session_usages
language plpgsql security invoker set search_path=public as $$
declare
  v_purchase public.purchases%rowtype;
  v_used integer;
  v_next_seq integer;
  v_deducted numeric(12,2);
  v_row public.session_usages%rowtype;
begin
  select * into v_purchase from public.purchases where id=p_purchase_id for update;
  if not found then raise exception '找不到購買紀錄'; end if;
  if v_purchase.status <> 'active' then raise exception '此課程不是有效狀態'; end if;
  select count(*) into v_used from public.session_usages where purchase_id=p_purchase_id;
  if v_used >= v_purchase.total_sessions then raise exception '剩餘堂數不足'; end if;
  select candidate.seq into v_next_seq
  from generate_series(1,v_purchase.total_sessions) as candidate(seq)
  where not exists (
    select 1 from public.session_usages usage
    where usage.purchase_id=p_purchase_id and usage.session_seq=candidate.seq
  )
  order by candidate.seq
  limit 1;
  if v_next_seq is null then raise exception '找不到可用的銷課堂次'; end if;
  if v_used + 1 = v_purchase.total_sessions then
    select round(v_purchase.total_amount-coalesce(sum(deducted_amount),0),2)
      into v_deducted from public.session_usages where purchase_id=p_purchase_id;
  else
    v_deducted := round(v_purchase.total_amount/v_purchase.total_sessions,2);
  end if;
  insert into public.session_usages(purchase_id,usage_date,coach_id,session_seq,deducted_amount,note,created_by)
  values(p_purchase_id,p_usage_date,p_coach_id,v_next_seq,v_deducted,nullif(trim(p_note),''),auth.uid()) returning * into v_row;
  insert into public.daily_operations(operation_date,coach_id,classes_held,classes_cancelled,trial_visits,trial_conversions)
  values(p_usage_date,p_coach_id,1,0,0,0)
  on conflict(operation_date,coach_id) do update
  set classes_held=(select count(*) from public.session_usages
                    where usage_date=p_usage_date and coach_id=p_coach_id);
  if v_used+1=v_purchase.total_sessions then update public.purchases set status='completed' where id=p_purchase_id; end if;
  return v_row;
end; $$;

alter table public.profiles enable row level security;
alter table public.members enable row level security;
alter table public.course_catalog enable row level security;
alter table public.daily_operations enable row level security;
alter table public.purchases enable row level security;
alter table public.purchase_payments enable row level security;
alter table public.session_usages enable row level security;
alter table public.trial_items enable row level security;
alter table public.operation_item_catalog enable row level security;
alter table public.single_sales enable row level security;
alter table public.event_supports enable row level security;
alter table public.session_cancellations enable row level security;

create policy profiles_read on public.profiles for select to authenticated using (active);
create policy profiles_admin_update on public.profiles for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy members_read on public.members for select to authenticated using (true);
create policy members_insert on public.members for insert to authenticated with check (created_by=auth.uid());
create policy course_catalog_read on public.course_catalog for select to authenticated using (true);
create policy course_catalog_admin_insert on public.course_catalog for insert to authenticated with check (public.is_admin());
create policy course_catalog_admin_update on public.course_catalog for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy course_catalog_admin_delete on public.course_catalog for delete to authenticated using (public.is_admin());
create policy daily_read on public.daily_operations for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy daily_insert on public.daily_operations for insert to authenticated with check (coach_id=auth.uid() or public.is_manager());
create policy daily_update on public.daily_operations for update to authenticated using (coach_id=auth.uid() or public.is_manager()) with check (coach_id=auth.uid() or public.is_manager());
create policy purchase_read on public.purchases for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy purchase_insert on public.purchases for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy purchase_update on public.purchases for update to authenticated
using (coach_id=auth.uid() or public.is_manager())
with check (coach_id=auth.uid() or public.is_manager());
create policy payment_read on public.purchase_payments for select to authenticated using (exists(select 1 from public.purchases p where p.id=purchase_id and (p.coach_id=auth.uid() or public.is_manager())));
create policy payment_insert on public.purchase_payments for insert to authenticated with check (created_by=auth.uid() and exists(select 1 from public.purchases p where p.id=purchase_id and (p.coach_id=auth.uid() or public.is_manager())));
create policy usage_read on public.session_usages for select to authenticated using (
  coach_id=auth.uid() or public.is_manager() or
  exists(select 1 from public.purchases p where p.id=purchase_id and p.coach_id=auth.uid())
);
create policy usage_insert on public.session_usages for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));

create policy trial_read on public.trial_items for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy operation_item_catalog_read on public.operation_item_catalog for select to authenticated using (true);
create policy trial_insert on public.trial_items for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy single_sale_read on public.single_sales for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy single_sale_insert on public.single_sales for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy event_read on public.event_supports for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy event_insert on public.event_supports for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy cancellation_read on public.session_cancellations for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy cancellation_insert on public.session_cancellations for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));

grant select on public.purchase_balances to authenticated;
grant execute on function public.consume_session(uuid,date,uuid,text) to authenticated;

