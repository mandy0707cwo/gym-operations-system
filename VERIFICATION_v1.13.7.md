# v1.13.7 驗證與發布狀態（2026-10-07）

## 狀態

- 正式資料庫修正已執行並驗證：migration project_coach_read_v1_13_7，資料庫版本 20261007015608（UTC；台北 2026-10-07 09:56:08）。
- 只調整 public.project_entries 的 SELECT 政策，不新增交易、不回填或改寫任何欄位。
- VERSION、App 預設備份版本及 Markdown 已更新 v1.13.7；本版基於 GitHub main c829e070 / v1.13.6，使用者於 2026-10-07 授權提交。GitHub 提交與 Streamlit 自動部署為不同狀態，不以提交成功推論畫面已驗收；不手動 Reboot。
- SQL 權限直接生效，不依賴程式重新部署。使用者須重新整理頁面或重新查詢；尚未以使用者密碼登入做畫面驗收。

## 權限與資料核對

- 以 SET LOCAL ROLE authenticated 及交易內 auth.uid() 身分設定，逐一測試正式 16 個 profiles 帳號；實際 RLS 可讀筆數符合既有建立者/管理角色及新增有效本人授課條件。測試完 RESET ROLE；未更動帳號、session、JWT、資料或角色授權。
- 使用者回報的管理員代登記錄已用授課教練真實資料庫角色核對可讀，區間時數合計符合原始記錄。其他教練且非本人建立的記錄不可讀。公開版本文件不列帳號、姓名或營運明細。
- 修正前後 project_entries 的筆數、金額合計、時數合計及全部欄位內容指紋一致；詳細對帳結果留存本機驗證紀錄，不將正式營運金額或資料指紋發布至原始碼庫。
- RLS 持續啟用；原 INSERT 政策 created_by=auth.uid() 保留；沒有新增 UPDATE、DELETE、函式、索引或 grant。
- 授課日期 entry_date 不變，created_by 不變。畫面與時數仍使用正常使用者的資料庫連線，不改成管理員連線繞過 RLS。

## 自動測試

- tests/test_project_coach_read.mjs：16 項隔離 PostgreSQL 測試通過，涵蓋代登可見、本人建立、其他教練隔離、管理員/主管/共用角色、停用與無身分、未登入、新增建立者防偽及修改/刪除權限不增加、原始值不變與安全重跑。
- tests/test_atomic_purchase.mjs：31 項隔離 PostgreSQL 既有購課交易測試通過，正式交易寫入 0。
- 六個既有模組共 96 項 Python 回歸測試通過：project_queries、project_queries_ui、financial_backup、general_usage_query、payment_net_allocation、purchase_installment_ui。
- 初次廣泛測試受 Windows 暫存目錄權限及缺少 openpyxl 影響，不能視為產品失敗；改用工作區測試暫存目錄，補入已內建的 openpyxl 路徑後，上述正式功能範圍重跑通過。暫停中的 activity_pilot 非本次修正或正式發布範圍，不隨本版上線。
- 正式發布用 App 從已驗證 v1.13.6 快照產生；只調整預設備份版本（另移除檔尾空行），保留原 SQL 升級提示 v1.13.6，不帶入本機活動方案入口。

## 既存安全提醒（非本次新增，未擴大修改）

執行前後 Supabase 安全檢查類型與數量一致：11 個匿名可呼叫 SECURITY DEFINER 提醒、13 個已登入可呼叫 SECURITY DEFINER 提醒，以及 1 個外洩密碼防護未啟用提醒。這些需另案逐項確認函式用途與既有呼叫鏈，不能直接全面撤權以免影響營運。

- [匿名函式執行權限說明](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
- [已登入函式執行權限說明](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)
- [密碼防護說明](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)

## 操作與復原

由回報教練重新整理每日營運專案頁，確認代登記錄；教練查詢的執行時數選擇涵蓋執行日期的區間並重新查詢。不得重複輸入原記錄。

政策前版本與復原 SQL 已列 UPGRADE_v1.13.7.md；只復原讀取條件，不還原或刪除交易。使用者授權提交本版檔案，GitHub 提交識別碼以提交紀錄為準；本機完整發布狀態另行留存。
