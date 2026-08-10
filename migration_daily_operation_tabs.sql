-- 每日營運三分頁與銷課取消紀錄（可在既有資料庫安全執行）
create table if not exists public.trial_items (
  id uuid primary key default gen_random_uuid(), entry_date date not null,
  content text not null check (length(trim(content)) > 0), hours numeric(5,2) not null check (hours > 0),
  coach_id uuid not null references public.profiles(id), created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id)
);
create table if not exists public.single_sales (
  id uuid primary key default gen_random_uuid(), entry_date date not null,
  content text not null check (length(trim(content)) > 0), hours numeric(5,2) not null check (hours > 0),
  coach_id uuid not null references public.profiles(id), created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id)
);
create table if not exists public.event_supports (
  id uuid primary key default gen_random_uuid(), entry_date date not null,
  content text not null check (length(trim(content)) > 0), hours numeric(5,2) not null check (hours > 0),
  deducted_hours numeric(5,2) not null default 0 check (deducted_hours >= 0 and deducted_hours <= hours),
  deduction_reason text, coach_id uuid not null references public.profiles(id), created_at timestamptz not null default now(),
  created_by uuid not null references public.profiles(id),
  check (deducted_hours = 0 or length(trim(deduction_reason)) > 0)
);
create table if not exists public.session_cancellations (
  id uuid primary key default gen_random_uuid(), cancel_date date not null,
  coach_id uuid not null references public.profiles(id), cancelled_sessions integer not null check (cancelled_sessions > 0),
  reason text, created_at timestamptz not null default now(), created_by uuid not null references public.profiles(id)
);
create index if not exists idx_trial_date_coach on public.trial_items(entry_date, coach_id);
create index if not exists idx_single_sale_date_coach on public.single_sales(entry_date, coach_id);
create index if not exists idx_event_date_coach on public.event_supports(entry_date, coach_id);
create index if not exists idx_cancel_date_coach on public.session_cancellations(cancel_date, coach_id);
alter table public.trial_items enable row level security;
alter table public.single_sales enable row level security;
alter table public.event_supports enable row level security;
alter table public.session_cancellations enable row level security;
drop policy if exists trial_read on public.trial_items;
drop policy if exists trial_insert on public.trial_items;
drop policy if exists single_sale_read on public.single_sales;
drop policy if exists single_sale_insert on public.single_sales;
drop policy if exists event_read on public.event_supports;
drop policy if exists event_insert on public.event_supports;
drop policy if exists cancellation_read on public.session_cancellations;
drop policy if exists cancellation_insert on public.session_cancellations;
create policy trial_read on public.trial_items for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy trial_insert on public.trial_items for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy single_sale_read on public.single_sales for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy single_sale_insert on public.single_sales for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy event_read on public.event_supports for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy event_insert on public.event_supports for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
create policy cancellation_read on public.session_cancellations for select to authenticated using (coach_id=auth.uid() or public.is_manager());
create policy cancellation_insert on public.session_cancellations for insert to authenticated with check (created_by=auth.uid() and (coach_id=auth.uid() or public.is_manager()));
