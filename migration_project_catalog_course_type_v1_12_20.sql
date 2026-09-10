-- v1.12.20：專案操作項目新增課程屬性。
-- 可重複執行；既有項目先標示為「未分類」，再由系統管理員逐筆修改。

alter table public.project_catalog
  add column if not exists course_type text;

update public.project_catalog
set course_type = '未分類'
where course_type is null or length(trim(course_type)) = 0;

alter table public.project_catalog
  alter column course_type set default '未分類',
  alter column course_type set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.project_catalog'::regclass
      and conname = 'project_catalog_course_type_not_blank'
  ) then
    alter table public.project_catalog
      add constraint project_catalog_course_type_not_blank
      check (length(trim(course_type)) > 0) not valid;
  end if;
end $$;

alter table public.project_catalog
  validate constraint project_catalog_course_type_not_blank;

select 'v1.12.20 專案操作項目課程屬性建立完成' as result;
