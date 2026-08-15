
select 'v1.6.0' as migration_version;

alter table public.operation_item_catalog
  add column if not exists active boolean not null default true;

create index if not exists operation_item_catalog_type_active_name_idx
  on public.operation_item_catalog(item_type,active,item_name);
