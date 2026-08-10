-- 體驗項目增加體驗會員姓名。既有紀錄保留，舊資料可為空白。
-- 可重複執行。

alter table public.trial_items
  add column if not exists member_name text;

alter table public.trial_items
  drop constraint if exists trial_items_member_name_check;

alter table public.trial_items
  add constraint trial_items_member_name_check
  check (member_name is null or length(trim(member_name)) > 0);
