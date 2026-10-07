-- v1.13.7：管理員代登的專案紀錄，授課教練本人也可讀取。
-- 僅調整 SELECT；保留建立者及既有主管/共用教練/管理員讀取權限。
-- 不新增或更改交易、日期、金額、時數、建立者及寫入權限。
alter policy project_entries_read on public.project_entries
  to authenticated
  using (
    created_by = (select auth.uid())
    or public.is_manager()
    or (
      coach_id = (select auth.uid())
      and exists (
        select 1 from public.profiles as actor
        where actor.id = (select auth.uid())
          and actor.role = 'coach'
          and actor.active
      )
    )
  );
