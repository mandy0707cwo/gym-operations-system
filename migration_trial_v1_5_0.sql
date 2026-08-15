
select 'v1.5.0' as migration_version;

alter table public.operation_item_catalog
  add column if not exists detail_content text;

alter table public.trial_items
  add column if not exists detail_content text;
