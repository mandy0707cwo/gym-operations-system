select 'v1.2.0' as migration_version;

alter table public.projects
  add column if not exists stored_date date;

alter table public.projects
  drop constraint if exists projects_stored_date_required;

alter table public.projects
  add constraint projects_stored_date_required
  check (funding_type <> 'stored' or stored_date is not null)
  not valid;
