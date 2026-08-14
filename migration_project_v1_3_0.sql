
select 'v1.3.0' as migration_version;

create table if not exists public.project_deposits (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id),
  deposit_date date not null,
  amount numeric(12,2) not null check (amount <> 0),
  transaction_type text not null default 'deposit' check (transaction_type in ('opening','deposit','reversal')),
  reversed_deposit_id uuid references public.project_deposits(id),
  note text,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);

create unique index if not exists project_deposits_one_reversal
  on public.project_deposits(reversed_deposit_id)
  where reversed_deposit_id is not null;
create index if not exists idx_project_deposits_project_date
  on public.project_deposits(project_id,deposit_date desc);

insert into public.project_deposits(project_id,deposit_date,amount,transaction_type,note,created_by)
select p.id,p.stored_date,p.stored_amount,'opening','系統轉入期初儲值',p.created_by
from public.projects p
where p.funding_type='stored' and p.stored_amount>0 and p.stored_date is not null
  and not exists(select 1 from public.project_deposits d where d.project_id=p.id);

alter table public.project_deposits enable row level security;
drop policy if exists project_deposits_read on public.project_deposits;
drop policy if exists project_deposits_admin_all on public.project_deposits;
create policy project_deposits_read on public.project_deposits
  for select to authenticated using (exists(select 1 from public.profiles where id=auth.uid() and active));
create policy project_deposits_admin_all on public.project_deposits
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

create or replace function public.add_project_deposit(
  p_project_id uuid,p_deposit_date date,p_amount numeric,p_note text default null
) returns public.project_deposits
language plpgsql security definer set search_path=public as $$
declare v_project public.projects%rowtype; v_deposit public.project_deposits%rowtype;
begin
  if not (coalesce(public.is_admin(),false) or auth.role()='service_role') then raise exception '僅系統管理員可新增專案儲值'; end if;
  if p_deposit_date is null then raise exception '儲值日期不可空白'; end if;
  if p_amount is null or p_amount<=0 then raise exception '儲值金額必須大於零'; end if;
  select * into v_project from public.projects where id=p_project_id for update;
  if not found or v_project.funding_type<>'stored' then raise exception '此專案不是已儲值專案'; end if;
  insert into public.project_deposits(project_id,deposit_date,amount,transaction_type,note,created_by)
  values(p_project_id,p_deposit_date,round(p_amount,2),'deposit',nullif(trim(p_note),''),auth.uid()) returning * into v_deposit;
  update public.projects set stored_amount=stored_amount+round(p_amount,2),updated_at=now() where id=p_project_id;
  return v_deposit;
end $$;

create or replace function public.reverse_project_deposit(
  p_deposit_id uuid,p_note text
) returns public.project_deposits
language plpgsql security definer set search_path=public as $$
declare v_original public.project_deposits%rowtype; v_reversal public.project_deposits%rowtype; v_used numeric(12,2); v_total numeric(12,2);
begin
  if not (coalesce(public.is_admin(),false) or auth.role()='service_role') then raise exception '僅系統管理員可沖銷專案儲值'; end if;
  if nullif(trim(p_note),'') is null then raise exception '沖銷原因不可空白'; end if;
  select * into v_original from public.project_deposits where id=p_deposit_id for update;
  if not found or v_original.amount<=0 then raise exception '找不到可沖銷的儲值紀錄'; end if;
  if exists(select 1 from public.project_deposits where reversed_deposit_id=v_original.id) then raise exception '此儲值紀錄已沖銷'; end if;
  select stored_amount into v_total from public.projects where id=v_original.project_id for update;
  select coalesce(sum(line_amount),0) into v_used from public.project_entries where project_id=v_original.project_id;
  if v_total-v_original.amount<v_used then raise exception '沖銷後儲值金額將低於已使用金額'; end if;
  insert into public.project_deposits(project_id,deposit_date,amount,transaction_type,reversed_deposit_id,note,created_by)
  values(v_original.project_id,current_date,-v_original.amount,'reversal',v_original.id,trim(p_note),auth.uid()) returning * into v_reversal;
  update public.projects set stored_amount=stored_amount-v_original.amount,updated_at=now() where id=v_original.project_id;
  return v_reversal;
end $$;

revoke all on function public.add_project_deposit(uuid,date,numeric,text) from public;
revoke all on function public.reverse_project_deposit(uuid,text) from public;
grant execute on function public.add_project_deposit(uuid,date,numeric,text) to authenticated,service_role;
grant execute on function public.reverse_project_deposit(uuid,text) to authenticated,service_role;
grant select on public.project_deposits to authenticated;
