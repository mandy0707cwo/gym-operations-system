
select 'v1.4.3' as migration_version;

alter table public.course_catalog
  add column if not exists active boolean not null default true;

create index if not exists idx_course_catalog_active_name
  on public.course_catalog(active,course_name);
