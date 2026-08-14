-- v1.1.2：非會員專案主檔、儲值／未儲值模式與專案財務報表資料（相容舊版財務保護觸發器）。
-- 可重複執行；不刪除先前任何專案或財務資料。

create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  project_name text not null unique check (length(trim(project_name)) > 0),
  funding_type text not null default 'unfunded' check (funding_type in ('stored','unfunded')),
  stored_amount numeric(12,2) not null default 0 check (stored_amount >= 0),
  active boolean not null default true,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((funding_type='stored' and stored_amount > 0) or (funding_type='unfunded' and stored_amount=0))
);

-- 既有專案先完整保留為未儲值；實際為已儲值者需由管理員輸入正確儲值金額。
insert into public.projects(project_name,funding_type,stored_amount,created_by)
select distinct pc.project_name,'unfunded',0,null::uuid
from public.project_catalog pc
where length(trim(pc.project_name))>0
on conflict(project_name) do nothing;

alter table public.project_catalog add column if not exists project_id uuid references public.projects(id);
update public.project_catalog pc set project_id=p.id
from public.projects p where pc.project_id is null and p.project_name=pc.project_name;

-- 移除先前試作儲值功能對舊專案紀錄的修改限制；舊資料表與歷史資料仍完整保留。
-- 觸發器名稱可能因舊版不同，依其呼叫的函式名稱找出並移除。
do $$
declare v_trigger record;
begin
  for v_trigger in
    select t.tgname
    from pg_trigger t
    join pg_proc p on p.oid=t.tgfoid
    where t.tgrelid='public.project_entries'::regclass
      and not t.tgisinternal
      and p.proname='protect_project_financial_history'
  loop
    execute format('drop trigger if exists %I on public.project_entries',v_trigger.tgname);
  end loop;
end $$;

alter table public.project_entries add column if not exists project_id uuid references public.projects(id);
alter table public.project_entries add column if not exists note text;
alter table public.project_entries add column if not exists line_amount numeric(12,2);
update public.project_entries set line_amount=round(quantity*unit_price,2) where line_amount is null;
alter table public.project_entries alter column line_amount set not null;
alter table public.project_entries drop constraint if exists project_entries_line_amount_nonnegative;
alter table public.project_entries add constraint project_entries_line_amount_nonnegative check (line_amount>=0) not valid;
update public.project_entries pe set project_id=p.id
from public.projects p where pe.project_id is null and p.project_name=pe.project_name;

create index if not exists idx_project_catalog_project on public.project_catalog(project_id);
create index if not exists idx_project_entries_project_date on public.project_entries(project_id,entry_date desc);

create or replace view public.project_funding_balances with (security_invoker=true) as
select p.id project_id,p.project_name,p.funding_type,p.stored_amount,
       coalesce(sum(pe.line_amount),0)::numeric(12,2) used_amount,
       (p.stored_amount-coalesce(sum(pe.line_amount),0))::numeric(12,2) remaining_amount
from public.projects p
left join public.project_entries pe on pe.project_id=p.id
group by p.id,p.project_name,p.funding_type,p.stored_amount;

create or replace function public.get_project_funding_status(p_project_id uuid)
returns table(stored_amount numeric,used_amount numeric,remaining_amount numeric)
language sql stable security definer set search_path=public as $$
  select b.stored_amount,b.used_amount,b.remaining_amount
  from public.project_funding_balances b
  where b.project_id=p_project_id
    and exists(select 1 from public.profiles p where p.id=auth.uid() and p.active);
$$;

create or replace function public.create_project_operation(
  p_entry_date date, p_catalog_id uuid, p_user_name text, p_coach_id uuid,
  p_quantity numeric, p_total_amount numeric, p_note text default null
) returns public.project_entries
language plpgsql security definer set search_path=public as $$
declare
  v_catalog public.project_catalog%rowtype;
  v_project public.projects%rowtype;
  v_used numeric(12,2);
  v_entry public.project_entries%rowtype;
begin
  if auth.uid() is null then raise exception '尚未登入'; end if;
  if not exists (
    select 1 from public.profiles where id=auth.uid() and active
      and (id=p_coach_id or role in ('shared_coach','manager','admin'))
  ) then raise exception '沒有權限替此教練建立專案紀錄'; end if;
  if nullif(trim(p_user_name),'') is null then raise exception '使用者不可空白'; end if;
  if p_quantity<=0 then raise exception '數量必須大於零'; end if;
  if p_total_amount<0 then raise exception '金額不可小於零'; end if;

  select * into v_catalog from public.project_catalog where id=p_catalog_id;
  if not found or v_catalog.project_id is null then raise exception '找不到專案操作項目'; end if;
  select * into v_project from public.projects where id=v_catalog.project_id and active for update;
  if not found then raise exception '此專案未啟用'; end if;

  if v_project.funding_type='stored' then
    select coalesce(sum(line_amount),0) into v_used
    from public.project_entries where project_id=v_project.id;
    if v_used+p_total_amount>v_project.stored_amount then
      raise exception '專案儲值餘額不足，目前剩餘金額：%',v_project.stored_amount-v_used;
    end if;
  end if;

  insert into public.project_entries(
    entry_date,project_catalog_id,project_id,project_name,person_name,coach_id,
    item_name,item_hours,quantity,unit_price,line_amount,note,created_by
  ) values (
    p_entry_date,v_catalog.id,v_project.id,v_project.project_name,trim(p_user_name),p_coach_id,
    v_catalog.item_name,v_catalog.hours,p_quantity,
    case when p_quantity=0 then 0 else round(p_total_amount/p_quantity,2) end,p_total_amount,
    nullif(trim(p_note),''),auth.uid()
  ) returning * into v_entry;
  return v_entry;
end; $$;

alter table public.projects enable row level security;
drop policy if exists projects_read on public.projects;
drop policy if exists projects_admin_all on public.projects;
create policy projects_read on public.projects for select to authenticated using (active or public.is_admin());
create policy projects_admin_all on public.projects for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

grant select on public.project_funding_balances to authenticated;
revoke all on function public.create_project_operation(date,uuid,text,uuid,numeric,numeric,text) from public;
revoke all on function public.get_project_funding_status(uuid) from public;
grant execute on function public.create_project_operation(date,uuid,text,uuid,numeric,numeric,text) to authenticated;
grant execute on function public.get_project_funding_status(uuid) to authenticated;
