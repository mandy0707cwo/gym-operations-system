-- 允許後續期款固定登錄第 2 期或第 3 期。
-- 保留同一購買紀錄不可重複期次，以及累計付款不可超過成交總金額的檢核。

alter table public.purchase_payments
  drop constraint if exists purchase_payments_installment_no_check;

alter table public.purchase_payments
  add constraint purchase_payments_installment_no_check
  check (installment_no between 1 and 3);

create or replace function public.validate_purchase_payment()
returns trigger language plpgsql set search_path=public as $$
declare
  v_purchase public.purchases%rowtype;
  v_paid numeric(12,2);
begin
  select * into v_purchase
  from public.purchases
  where id=new.purchase_id
  for update;

  select coalesce(sum(amount),0) into v_paid
  from public.purchase_payments
  where purchase_id=new.purchase_id
    and id<>new.id;

  if v_paid + new.amount > v_purchase.total_amount then
    raise exception '累計付款金額不可超過成交總金額';
  end if;

  return new;
end;
$$;
