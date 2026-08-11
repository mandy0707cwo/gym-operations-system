-- 體驗項目及單堂銷售新增備註欄位；可重複執行。

alter table public.trial_items
  add column if not exists note text;

alter table public.single_sales
  add column if not exists note text;
