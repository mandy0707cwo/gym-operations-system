select 'v1.11.8' as migration_version;

alter table public.trial_items
  add column if not exists course_type text;

alter table public.single_sales
  add column if not exists course_type text;

update public.trial_items as trial
set course_type = catalog.course_type
from public.operation_item_catalog as catalog
where trial.course_type is null
  and catalog.item_type = 'trial'
  and trim(catalog.item_name) = trim(trial.content)
  and coalesce(trim(catalog.detail_content), '') = coalesce(trim(trial.detail_content), '')
  and nullif(trim(catalog.course_type), '') is not null;

update public.single_sales as sale
set course_type = catalog.course_type
from public.operation_item_catalog as catalog
where sale.course_type is null
  and catalog.item_type = 'single_sale'
  and trim(catalog.item_name) = trim(sale.content)
  and nullif(trim(catalog.course_type), '') is not null;

comment on column public.trial_items.course_type is
  '建立體驗項目紀錄時保存的課程屬性快照。';

comment on column public.single_sales.course_type is
  '建立單堂銷售紀錄時保存的課程屬性快照。';

