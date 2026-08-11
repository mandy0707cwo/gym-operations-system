-- 為既有課程名稱增加課程種類；可重複執行。
alter table public.course_catalog
  add column if not exists course_type text;

update public.course_catalog
set course_type = '未分類'
where course_type is null or length(trim(course_type)) = 0;

alter table public.course_catalog
  alter column course_type set default '未分類',
  alter column course_type set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'course_catalog_course_type_not_blank'
      and conrelid = 'public.course_catalog'::regclass
  ) then
    alter table public.course_catalog
      add constraint course_catalog_course_type_not_blank
      check (length(trim(course_type)) > 0);
  end if;
end $$;
