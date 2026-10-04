# v1.13.6 升級與操作

日期：2026-10-05。狀態：正式 SQL 已執行並驗證；使用者已同意提交及部署，線上完成狀態以部署紀錄為準。

## 升級順序

1. 先備份正式資料庫；不得直接覆寫備份。
2. 在正確的 gym-operations Supabase 專案執行 migration_atomic_purchase_v1_13_6.sql，只新增原子購課函式及函式執行權限，不改寫歷史交易、RLS 或資料表。
3. 唯讀核對函式簽章、SECURITY INVOKER、search_path、匿名不可執行及 authenticated 可執行：

```sql
select p.oid::regprocedure as signature,p.prosecdef,p.proconfig,
       has_function_privilege('anon',p.oid,'execute') as anon_execute,
       has_function_privilege('authenticated',p.oid,'execute') as authenticated_execute
from pg_proc p
where p.oid='public.create_purchase_with_first_payment(jsonb,jsonb)'::regprocedure;
```

預期 prosecdef=false、search_path 空白、anon_execute=false、authenticated_execute=true；並確認原 purchases 及 purchase_payments RLS 仍啟用。

4. 再部署 app.py 與 VERSION=v1.13.6，同步本版文件及測試。若 APP_VERSION 有設定，同步改為 v1.13.6。
5. 先登入唯讀驗證分頁及權限，再由使用者指定可用測試客戶授權實際交易驗收；不要為測試擅自建立正式金流。

本版包含未發布的 v1.13.5 三分頁，不需先獨立部署 v1.13.5。舊 App 可與新增函式共存；新版 App 若尚無函式，會停止購課，不退回舊寫法。

## 操作

購買及分期 → 課程購買：選客戶、付款方式及課程，確認教練、轉介、備註及時數，再填堂數、金額、購課及有效日期。分期另填總期數、首期金額及支付日期。

按確認後，購課及首期付款兩筆都成功才儲存並清空；資料庫拒絕任一步都不建立兩筆。後續期款仍選原購課，不新增 purchase_id；課程中止僅管理員操作，計算規則不變。

## 注意與復原

- 連線中斷可能只是成功回覆未送達，這時兩筆都已儲存；先查核，不能直接重送。本版未加入持久化去重識別碼。
- 正式 SQL 已執行；線上部署結果以部署紀錄為準。原歷史中可能存在的部分寫入不會自動補款或刪除，需另行授權查核。
- 復原時先還原已發布 App 與版本；可保留未被舊 App 呼叫的新函式，不刪交易或付款。還原舊 App 會恢復原兩次寫入的限制。
- 不上傳本機活動試行、測試環境、虛構資料、套件快取或憑證。以最新已發布主線移植本版必要函式及導覽，不直接上傳混有本機試行程式的整份 app.py。
