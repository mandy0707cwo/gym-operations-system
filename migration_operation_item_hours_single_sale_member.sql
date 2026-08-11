-- 新增體驗／單堂銷售項目的預設時數，以及單堂銷售會員姓名。
-- 可重複執行。既有單堂銷售資料以「未填姓名」補值，避免破壞歷史紀錄。

alter table public.operation_item_catalog
  add column if not exists session_hours numeric(5,2) not null default 1;

alter table public.operation_item_catalog
  drop constraint if exists operation_item_catalog_session_hours_check;

alter table public.operation_item_catalog
  add constraint operation_item_catalog_session_hours_check check (session_hours > 0);

alter table public.single_sales
  add column if not exists member_name text;

update public.single_sales
set member_name = '未填姓名'
where member_name is null or length(trim(member_name)) = 0;

alter table public.single_sales
  alter column member_name set not null;

alter table public.single_sales
  drop constraint if exists single_sales_member_name_check;

alter table public.single_sales
  add constraint single_sales_member_name_check check (length(trim(member_name)) > 0);
