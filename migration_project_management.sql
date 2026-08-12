-- 專案管理與每日營運專案紀錄。可重複執行。

create table if not exists public.project_catalog (
  id uuid primary key default gen_random_uuid(),
  project_name text not null check (length(trim(project_name)) > 0),
  item_name text not null check (length(trim(item_name)) > 0),
  hours numeric(8,2) not null check (hours > 0),
  price numeric(12,2) not null check (price >= 0),
  created_at timestamptz not null default now(),
  unique (project_name, item_name)
);

create table if not exists public.project_entries (
  id uuid primary key default gen_random_uuid(),
  entry_date date not null,
  project_catalog_id uuid not null references public.project_catalog(id),
  project_name text not null,
  person_name text not null check (length(trim(person_name)) > 0),
  coach_id uuid references public.profiles(id),
  item_name text not null,
  item_hours numeric(8,2) check (item_hours > 0),
  quantity numeric(10,2) not null check (quantity > 0),
  unit_price numeric(12,2) not null check (unit_price >= 0),
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now()
);

-- 既有專案資料表升級：新增教練及項目時數快照。
alter table public.project_entries add column if not exists coach_id uuid references public.profiles(id);
alter table public.project_entries add column if not exists item_hours numeric(8,2) check (item_hours > 0);

create index if not exists idx_project_entries_date on public.project_entries(entry_date desc);
create index if not exists idx_project_entries_catalog on public.project_entries(project_catalog_id);
create index if not exists idx_project_entries_coach on public.project_entries(coach_id);

alter table public.project_catalog enable row level security;
alter table public.project_entries enable row level security;

drop policy if exists project_catalog_read on public.project_catalog;
drop policy if exists project_catalog_admin_insert on public.project_catalog;
drop policy if exists project_catalog_admin_update on public.project_catalog;
drop policy if exists project_catalog_admin_delete on public.project_catalog;
drop policy if exists project_entries_read on public.project_entries;
drop policy if exists project_entries_insert on public.project_entries;

create policy project_catalog_read on public.project_catalog
  for select to authenticated using (true);
create policy project_catalog_admin_insert on public.project_catalog
  for insert to authenticated with check (public.is_admin());
create policy project_catalog_admin_update on public.project_catalog
  for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy project_catalog_admin_delete on public.project_catalog
  for delete to authenticated using (public.is_admin());
create policy project_entries_read on public.project_entries
  for select to authenticated using (created_by=auth.uid() or public.is_manager());
create policy project_entries_insert on public.project_entries
  for insert to authenticated with check (created_by=auth.uid());
