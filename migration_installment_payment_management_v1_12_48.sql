-- v1.12.48 分期付款更正與補繳管理
-- 執行後，只有啟用中的系統管理員可更正原付款或新增不占期次的補繳款。

alter table public.purchase_payments
  add column if not exists payment_kind text not null default 'installment';

alter table public.purchase_payments
  drop constraint if exists purchase_payments_payment_kind_check;

alter table public.purchase_payments
  add constraint purchase_payments_payment_kind_check
  check (payment_kind in ('installment','supplement'));

alter table public.purchase_payments
  drop constraint if exists purchase_payments_purchase_id_installment_no_key;

create unique index if not exists purchase_payments_regular_installment_key
  on public.purchase_payments(purchase_id,installment_no)
  where payment_kind='installment';

create table if not exists public.purchase_payment_change_logs (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid references public.purchase_payments(id) on delete restrict,
  purchase_id uuid not null references public.purchases(id) on delete restrict,
  action_type text not null check (action_type in ('correction','supplement')),
  installment_no smallint not null check (installment_no between 1 and 3),
  old_amount numeric(12,2),
  new_amount numeric(12,2) not null check (new_amount > 0),
  old_paid_date date,
  new_paid_date date not null,
  reason text not null check (length(trim(reason)) > 0),
  changed_by uuid not null references public.profiles(id),
  changed_at timestamptz not null default now()
);

alter table public.purchase_payment_change_logs enable row level security;

drop policy if exists payment_change_logs_admin_read on public.purchase_payment_change_logs;
create policy payment_change_logs_admin_read
on public.purchase_payment_change_logs for select
to authenticated
using (public.is_admin());

create index if not exists idx_payment_change_logs_purchase_changed
  on public.purchase_payment_change_logs(purchase_id,changed_at desc);

create or replace function public.admin_correct_purchase_payment(
  p_payment_id uuid,
  p_amount numeric,
  p_paid_date date,
  p_reason text
)
returns void
language plpgsql
security definer
set search_path=public
as $$
declare
  v_payment public.purchase_payments%rowtype;
begin
  if not public.is_admin() then
    raise exception '僅系統管理員可以更正付款紀錄';
  end if;
  if p_amount is null or p_amount <= 0 then
    raise exception '正確支付金額必須大於零';
  end if;
  if p_paid_date is null then
    raise exception '正確付款日期不可空白';
  end if;
  if nullif(trim(p_reason),'') is null then
    raise exception '更正原因不可空白';
  end if;

  select * into v_payment
  from public.purchase_payments
  where id=p_payment_id
  for update;
  if not found then
    raise exception '找不到付款紀錄';
  end if;
  if v_payment.payment_kind <> 'installment' then
    raise exception '補繳款不可由原付款更正功能修改';
  end if;

  update public.purchase_payments
  set amount=p_amount, paid_date=p_paid_date
  where id=p_payment_id;

  insert into public.purchase_payment_change_logs(
    payment_id,purchase_id,action_type,installment_no,
    old_amount,new_amount,old_paid_date,new_paid_date,reason,changed_by
  ) values (
    v_payment.id,v_payment.purchase_id,'correction',v_payment.installment_no,
    v_payment.amount,p_amount,v_payment.paid_date,p_paid_date,trim(p_reason),auth.uid()
  );
end;
$$;

create or replace function public.admin_add_purchase_payment_supplement(
  p_purchase_id uuid,
  p_amount numeric,
  p_paid_date date,
  p_reason text
)
returns uuid
language plpgsql
security definer
set search_path=public
as $$
declare
  v_purchase public.purchases%rowtype;
  v_paid numeric(12,2);
  v_regular_count integer;
  v_payment_id uuid;
begin
  if not public.is_admin() then
    raise exception '僅系統管理員可以登錄補繳款';
  end if;
  if p_amount is null or p_amount <= 0 then
    raise exception '補繳金額必須大於零';
  end if;
  if p_paid_date is null then
    raise exception '補繳日期不可空白';
  end if;
  if nullif(trim(p_reason),'') is null then
    raise exception '補繳原因不可空白';
  end if;

  select * into v_purchase
  from public.purchases
  where id=p_purchase_id
  for update;
  if not found then
    raise exception '找不到購買紀錄';
  end if;
  if v_purchase.payment_plan <> 'installment' then
    raise exception '只有分期購買可以登錄補繳款';
  end if;

  select coalesce(sum(amount),0) into v_paid
  from public.purchase_payments
  where purchase_id=p_purchase_id;
  select count(distinct installment_no) into v_regular_count
  from public.purchase_payments
  where purchase_id=p_purchase_id and payment_kind='installment';
  if v_regular_count < v_purchase.installment_count then
    raise exception '尚有原分期期次未登錄，請先完成原期款登錄';
  end if;
  if v_paid >= v_purchase.total_amount then
    raise exception '此購買紀錄已付清';
  end if;
  if v_paid + p_amount > v_purchase.total_amount then
    raise exception '補繳金額不可超過未付餘額';
  end if;

  insert into public.purchase_payments(
    purchase_id,installment_no,amount,paid_date,created_by,payment_kind
  ) values (
    p_purchase_id,v_purchase.installment_count,p_amount,p_paid_date,auth.uid(),'supplement'
  ) returning id into v_payment_id;

  insert into public.purchase_payment_change_logs(
    payment_id,purchase_id,action_type,installment_no,
    old_amount,new_amount,old_paid_date,new_paid_date,reason,changed_by
  ) values (
    v_payment_id,p_purchase_id,'supplement',v_purchase.installment_count,
    null,p_amount,null,p_paid_date,trim(p_reason),auth.uid()
  );

  return v_payment_id;
end;
$$;

revoke all on table public.purchase_payment_change_logs from anon;
grant select on table public.purchase_payment_change_logs to authenticated;

revoke all on function public.admin_correct_purchase_payment(uuid,numeric,date,text) from public,anon;
revoke all on function public.admin_add_purchase_payment_supplement(uuid,numeric,date,text) from public,anon;
grant execute on function public.admin_correct_purchase_payment(uuid,numeric,date,text) to authenticated;
grant execute on function public.admin_add_purchase_payment_supplement(uuid,numeric,date,text) to authenticated;

notify pgrst,'reload schema';
