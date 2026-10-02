-- v1.12.56：教練可查詢及修改全部客戶；僅系統管理員可刪除無購課紀錄的客戶。

drop policy if exists members_read on public.members;
create policy members_read on public.members
for select to authenticated
using (
  exists (
    select 1 from public.profiles
    where id=(select auth.uid())
      and role in ('coach','shared_coach','manager','admin')
      and active
  )
);

drop policy if exists members_update on public.members;
create policy members_update on public.members
for update to authenticated
using (
  exists (
    select 1 from public.profiles
    where id=(select auth.uid())
      and role in ('coach','shared_coach','manager','admin')
      and active
  )
)
with check (
  exists (
    select 1 from public.profiles
    where id=(select auth.uid())
      and role in ('coach','shared_coach','manager','admin')
      and active
  )
);

drop policy if exists members_delete on public.members;
create policy members_delete on public.members
for delete to authenticated
using ((select public.is_admin()));

-- 客戶刪除時一併移除其欄位修改紀錄；購課資料仍採 restrict，故有購課者無法刪除。
alter table public.member_change_logs
  drop constraint if exists member_change_logs_member_id_fkey;
alter table public.member_change_logs
  add constraint member_change_logs_member_id_fkey
  foreign key (member_id) references public.members(id) on delete cascade;

select 'v1.12.56 客戶完整查詢修改與安全刪除權限建立完成' as result;
