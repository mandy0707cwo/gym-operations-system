-- 僅供operations_db.py固定本機假資料庫；不是正式migration。
create role anon nologin;
create role authenticated nologin;
create schema auth;
grant usage on schema auth to anon,authenticated;
create function auth.uid() returns uuid language sql stable set search_path='' as $$
  select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid;
$$;
create table public.profiles(id uuid primary key,role text not null,active boolean not null);
insert into public.profiles values
('00000000-0000-4000-8000-000000000001','admin',true),
('00000000-0000-4000-8000-000000000002','manager',true),
('00000000-0000-4000-8000-000000000003','coach',true),
('00000000-0000-4000-8000-000000000004','shared_coach',true),
('00000000-0000-4000-8000-000000000005','manager',false);
alter table public.profiles enable row level security;
create policy self_profile on public.profiles for select to authenticated using (id=auth.uid());
grant select on public.profiles to authenticated;

create table public.purchases(id uuid primary key,purchase_date date not null,total_sessions int not null);
create table public.session_usages(id uuid primary key,purchase_id uuid not null references public.purchases(id),usage_date date not null);
create table public.course_terminations(id uuid primary key,purchase_id uuid not null references public.purchases(id),termination_date date not null,reversed_at timestamptz);
alter table public.purchases enable row level security;
alter table public.session_usages enable row level security;
alter table public.course_terminations enable row level security;
grant select on public.purchases,public.session_usages,public.course_terminations to authenticated;
create policy management_read on public.purchases for select to authenticated using (
 exists(select 1 from public.profiles where id=auth.uid() and active and role in ('manager','admin','shared_coach')));
create policy management_read on public.session_usages for select to authenticated using (
 exists(select 1 from public.profiles where id=auth.uid() and active and role in ('manager','admin','shared_coach')));
create policy admin_only on public.course_terminations for select to authenticated using (
 exists(select 1 from public.profiles where id=auth.uid() and active and role='admin'));

insert into public.purchases
select ('10000000-0000-4000-8000-'||lpad(n::text,12,'0'))::uuid,
       case when n=1 then '2026-09-01'::date else '2026-10-01'::date end,
       case when n in (1,3) then 2 else 1 end
from generate_series(1,9) n;
insert into public.session_usages
select ('20000000-0000-4000-8000-'||lpad(n::text,12,'0'))::uuid,
       ('10000000-0000-4000-8000-'||lpad(course::text,12,'0'))::uuid,day::date
from (values (1,1,'2026-09-30'),(2,1,'2026-10-02'),(3,2,'2026-10-07'),
 (4,3,'2026-10-11'),(5,4,'2026-10-12'),(6,5,'2026-10-14'),
 (7,6,'2026-10-16'),(8,7,'2026-10-20'),(9,8,'2026-11-02'),(10,9,'2026-10-07')) x(n,course,day);
insert into public.course_terminations values
('30000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000004','2026-10-10',null),
('30000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000005','2026-10-13','2026-10-15 00:00:00+08'),
('30000000-0000-4000-8000-000000000003','10000000-0000-4000-8000-000000000006','2026-10-13','2026-10-15 00:00:00+08'),
('30000000-0000-4000-8000-000000000004','10000000-0000-4000-8000-000000000007','2026-10-21',null);
