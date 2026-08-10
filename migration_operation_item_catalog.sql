-- 允許銷課取消堂數為 0，並建立體驗／單堂銷售下拉選項資料表。
-- 可重複執行。

alter table public.session_cancellations
  drop constraint if exists session_cancellations_cancelled_sessions_check;

alter table public.session_cancellations
  add constraint session_cancellations_cancelled_sessions_check
  check (cancelled_sessions >= 0);

create table if not exists public.operation_item_catalog (
  id uuid primary key default gen_random_uuid(),
  item_type text not null check (item_type in ('trial','single_sale')),
  item_name text not null check (length(trim(item_name)) > 0),
  created_at timestamptz not null default now(),
  unique (item_type, item_name)
);

alter table public.operation_item_catalog enable row level security;

drop policy if exists operation_item_catalog_read on public.operation_item_catalog;
create policy operation_item_catalog_read
  on public.operation_item_catalog for select to authenticated using (true);
