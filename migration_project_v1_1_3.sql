-- v1.1.3：解除舊版專案錢包交易對專案紀錄刪除的阻擋。
-- 保留 project_wallet_transactions 歷史資料；刪除 project_entries 時僅清空其關聯欄位。

do $$
begin
  if to_regclass('public.project_wallet_transactions') is not null then
    alter table public.project_wallet_transactions
      alter column project_entry_id drop not null;

    alter table public.project_wallet_transactions
      drop constraint if exists project_wallet_transactions_project_entry_id_fkey;

    alter table public.project_wallet_transactions
      add constraint project_wallet_transactions_project_entry_id_fkey
      foreign key (project_entry_id)
      references public.project_entries(id)
      on delete set null;
  end if;
end $$;
