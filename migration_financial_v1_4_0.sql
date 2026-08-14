
select 'v1.4.0' as migration_version;

alter table public.operation_item_catalog
  add column if not exists default_amount numeric(12,2) not null default 0;
alter table public.operation_item_catalog
  drop constraint if exists operation_item_catalog_default_amount_nonnegative;
alter table public.operation_item_catalog
  add constraint operation_item_catalog_default_amount_nonnegative check (default_amount>=0) not valid;

alter table public.trial_items
  add column if not exists amount numeric(12,2) not null default 0;
alter table public.trial_items
  drop constraint if exists trial_items_amount_nonnegative;
alter table public.trial_items
  add constraint trial_items_amount_nonnegative check (amount>=0) not valid;

alter table public.single_sales
  add column if not exists amount numeric(12,2) not null default 0;
alter table public.single_sales
  drop constraint if exists single_sales_amount_nonnegative;
alter table public.single_sales
  add constraint single_sales_amount_nonnegative check (amount>=0) not valid;
