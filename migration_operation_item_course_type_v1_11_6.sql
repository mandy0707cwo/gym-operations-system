select 'v1.11.6' as migration_version;

alter table public.operation_item_catalog
  add column if not exists course_type text;

comment on column public.operation_item_catalog.course_type is
  '體驗項目及單堂銷售項目的課程屬性；既有資料可為空白。';

