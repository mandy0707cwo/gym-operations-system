-- v1.12.39：新增課程報表分類；可重複執行。

alter table public.course_catalog
  add column if not exists report_category text;

update public.course_catalog
set report_category = '未分類'
where report_category is null or length(trim(report_category)) = 0;

alter table public.course_catalog
  alter column report_category set default '未分類',
  alter column report_category set not null;

alter table public.purchases
  add column if not exists report_category text;

-- 既有購買紀錄依課程名稱帶入目前的報表分類；尚未設定者保留「未分類」。
update public.purchases p
set report_category = coalesce(nullif(trim(c.report_category), ''), '未分類')
from public.course_catalog c
where trim(p.course_name) = trim(c.course_name)
  and (p.report_category is null or length(trim(p.report_category)) = 0);

update public.purchases
set report_category = '未分類'
where report_category is null or length(trim(report_category)) = 0;

alter table public.purchases
  alter column report_category set default '未分類',
  alter column report_category set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'course_catalog_report_category_not_blank'
      and conrelid = 'public.course_catalog'::regclass
  ) then
    alter table public.course_catalog
      add constraint course_catalog_report_category_not_blank
      check (length(trim(report_category)) > 0);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'purchases_report_category_not_blank'
      and conrelid = 'public.purchases'::regclass
  ) then
    alter table public.purchases
      add constraint purchases_report_category_not_blank
      check (length(trim(report_category)) > 0);
  end if;
end $$;
