-- 已上線專案升級：新增系統帳號登入與 admin 權限。請在 Supabase SQL Editor 執行一次。
alter type public.app_role add value if not exists 'admin';
commit;

alter table public.profiles add column if not exists username text;
create unique index if not exists profiles_username_lower_unique
  on public.profiles(lower(username)) where username is not null;

do $$ begin
  alter table public.profiles add constraint profiles_username_format
    check (username is null or username ~ '^[a-z0-9_]{3,30}$');
exception when duplicate_object then null;
end $$;

-- 將最早建立的現有主管升級為第一位系統管理員。
update public.profiles set role='admin'
where id=(select id from public.profiles where role='manager' order by created_at limit 1)
  and not exists(select 1 from public.profiles where role='admin');

create or replace function public.is_manager()
returns boolean language sql stable security definer set search_path = public
as $$ select exists(select 1 from public.profiles where id=auth.uid() and role in ('manager','admin') and active); $$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public
as $$ select exists(select 1 from public.profiles where id=auth.uid() and role='admin' and active); $$;

drop policy if exists profiles_manager_update on public.profiles;
drop policy if exists profiles_admin_update on public.profiles;
create policy profiles_admin_update on public.profiles for update to authenticated
  using (public.is_admin()) with check (public.is_admin());

