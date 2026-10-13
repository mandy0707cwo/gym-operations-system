-- v1.13.10：課程名稱管理的選填購課預設。先備份 course_catalog，再由管理員執行。
-- 僅新增欄位及檢核，不填入任何價格／堂數，不改既有購課與 RLS。
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.course_catalog
  add column if not exists default_sessions integer,
  add column if not exists default_total_amount numeric(12,2),
  add column if not exists note text;

do $migration$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='public.course_catalog'::regclass and conname='course_catalog_default_sessions_valid'
  ) then
    alter table public.course_catalog add constraint course_catalog_default_sessions_valid
      check (default_sessions is null or default_sessions between 1 and 999);
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid='public.course_catalog'::regclass and conname='course_catalog_default_total_amount_valid'
  ) then
    alter table public.course_catalog add constraint course_catalog_default_total_amount_valid
      check (default_total_amount is null or (default_total_amount > 0 and default_total_amount <= 10000000));
  end if;
end;
$migration$;

comment on column public.course_catalog.default_sessions is '購課預設堂數；NULL 表示未設定，不回填既有購課';
comment on column public.course_catalog.default_total_amount is '購課預設成交總金額（含稅）；NULL 表示未設定，購課時可調整';
comment on column public.course_catalog.note is '課程預設備註；購課時與客戶備註分行帶入，不覆寫歷史購課備註';

notify pgrst, 'reload schema';
commit;
