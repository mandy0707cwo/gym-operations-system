-- v1.12.26：教練可修改權限範圍內的客戶，並保留不可竄改的後台稽核紀錄。
-- 可重複執行；不刪除、不改寫既有客戶、購課、付款或銷課資料。

create or replace function public.audit_member_change()
returns trigger
language plpgsql
security definer
set search_path=pg_catalog,public
as $$
begin
  new.updated_at=now();
  if auth.uid() is not null then
    new.updated_by=auth.uid();
  end if;
  if to_jsonb(new) is distinct from to_jsonb(old) then
    insert into public.member_change_logs(member_id,changed_by,old_data,new_data)
    values(new.id,new.updated_by,to_jsonb(old),to_jsonb(new));
  end if;
  return new;
end;
$$;

revoke all on function public.audit_member_change() from public;

drop trigger if exists members_audit_update on public.members;
create trigger members_audit_update
before update on public.members
for each row execute function public.audit_member_change();

drop policy if exists members_update on public.members;
create policy members_update on public.members
for update to authenticated
using (
  (select public.is_manager())
  or created_by=(select auth.uid())
  or responsible_coach_id=(select auth.uid())
  or exists (
    select 1 from public.purchases p
    where p.member_id=members.id and p.coach_id=(select auth.uid())
  )
)
with check (
  (select public.is_manager())
  or created_by=(select auth.uid())
  or responsible_coach_id=(select auth.uid())
  or exists (
    select 1 from public.purchases p
    where p.member_id=members.id and p.coach_id=(select auth.uid())
  )
);

select 'v1.12.26 教練客戶修改權限建立完成' as result;
