-- v1.2.0：專案新增儲值日期。
-- 既有已儲值專案不自行假設日期；管理員下次修改時必須補登正確日期。

alter table public.projects
  add column if not exists stored_date date;

alter table public.projects
  drop constraint if exists projects_stored_date_required;

alter table public.projects
  add constraint projects_stored_date_required
  check (funding_type <> 'stored' or stored_date is not null)
  not valid;
