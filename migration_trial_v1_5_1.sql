
select 'v1.5.1' as migration_version;

alter table public.operation_item_catalog
  drop constraint if exists operation_item_catalog_item_type_item_name_key;

drop index if exists public.operation_item_catalog_non_trial_name_uidx;
drop index if exists public.operation_item_catalog_trial_name_content_uidx;

create unique index operation_item_catalog_non_trial_name_uidx
  on public.operation_item_catalog(item_type,item_name)
  where item_type <> 'trial';

create unique index operation_item_catalog_trial_name_content_uidx
  on public.operation_item_catalog(item_type,item_name,coalesce(detail_content,''))
  where item_type = 'trial';
