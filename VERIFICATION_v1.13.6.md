# v1.13.6 驗證紀錄

日期：2026-10-05。狀態：正式 SQL 已執行並驗證；使用者已同意提交及部署，線上完成狀態以部署紀錄為準。

## 結果

- 隔離 PostgreSQL：31 項通過。成功產生 5 組虛構購課及首期付款，數量一一對應；任一失敗測試前後購課及付款數均不增加。
- 實際測試包括：migration 安全重跑、函式 invoker/search_path/執行權限、admin/coach/manager/shared_coach 成功、一次付清、付款 trigger 拋錯及付款 RLS 拒絕時購課一併回滾、金額/日期/期數/主檔/偽造建立者檢核、停用與未登入拒絕、教練範圍及過去日期拒絕。
- Streamlit AppTest：22 項通過。新增單次 RPC、完整回傳才清空、第二步失敗無部分資料、缺函式不退回舊流程、未知回覆保留且不自動重試；包含原三分頁與中止權限檢核。
- 既有專案計算/Excel 35 項、專案介面 11 項、銷課查詢 7 項、付款未稅分配 21 項、財務備份 37 項通過，共 111 項。
- 總計 164 項。Python 語法檢查通過。採用 Supabase Python 2.18.1 固定依賴的 PostgREST 1.1.1 原始碼檢查，RPC 使用 SingleAPIResponse，可接收 JSON 物件；未宣稱完成正式 API 測試。

## 環境與限制

隔離環境為 PGlite 0.5.8 / PostgreSQL 18.3；正式 metadata 為 PostgreSQL 17.6.1.155。測試抽取專案既有購課/付款結構、RLS 與 trigger，補入已唯讀確認的課程啟用欄位，全部資料皆虛構。沒有本機網路資料庫服務或 Streamlit 服務。

正式 migration atomic_purchase_v1_13_6 已執行（資料庫 migration 版本 20261004165035）。唯讀核對函式本文與本版 SQL 一致、SECURITY INVOKER、空 search_path、anon 不可執行及 authenticated 可執行；原購課及付款 RLS、政策維持不變。執行前後資料筆數及金額合計相同，沒有改寫歷史交易或建立測試交易。沒有讀取會員交易明細或呼叫正式新購課函式。隔離測試不取代角色登入及實際 PostgREST 交易驗收。

本機 Supabase CLI 未安裝，官方 CLI 二進位下載逾時；SQL 依專案既有版本化檔名保存，使用 Supabase 連線工具執行並記錄 migration 歷史。PGlite 套件僅安裝於 output/qa_atomic_runtime，固定版本及保留鎖檔，未變更 App 依賴。

## 重現

有安裝原專案依賴的 Python 環境：

```powershell
python -X utf8 -m py_compile app.py
python -X utf8 -m unittest discover -s tests -p test_purchase_installment_ui.py
python -X utf8 -m unittest discover -s tests -p test_project_queries_ui.py
```

Node.js 及 npm 可用時，隔離 PostgreSQL 測試：

```powershell
npm install --prefix output/qa_atomic_runtime --ignore-scripts @electric-sql/pglite@0.5.8
node tests/test_atomic_purchase.mjs
```

## 既有安全警示（未修改）

正式安全顧問列出 11 個 anon 可執行、13 個 authenticated 可執行的 SECURITY DEFINER 函式，以及外洩密碼保護未開啟。包含角色查詢及專案函式，不能單憑可執行就認定可越權；需逐一檢查函式內部授權。

本次新函式採 INVOKER、撤銷 PUBLIC/anon 執行權，並於隔離環境確認匿名不可執行，未為通過測試而停用 RLS。既有警示超出本次購課交易範圍，未擅自修改：

- [匿名函式執行權檢核與處理](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
- [登入者函式執行權檢核與處理](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)
- [外洩密碼保護說明](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)

## 設計依據

採資料庫函式完成同一交易，例外不吞掉，由 PostgreSQL 整筆回滾。參考 [Supabase Database Functions](https://supabase.com/docs/guides/database/functions)、[PostgreSQL Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html)。歷史金額及會計公式未變更，未執行自動補款、刪除或未知結果重試。
