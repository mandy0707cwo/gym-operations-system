-- 僅供 127.0.0.1 的虛構資料測試；不是正式 Supabase 升級。
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema auth;
create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}'::jsonb);
create function auth.uid() returns uuid language sql stable as $$
select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid;
$$;
create function auth.role() returns text language sql stable as $$
select current_setting('request.jwt.claim.role',true);
$$;
grant usage on schema auth to authenticated,anon,service_role;
grant execute on all functions in schema auth to authenticated,anon,service_role;
