# v1.13.8 驗證紀錄（2026-10-12）

## 準備階段狀態（正式執行前）

本機候選版本，非線上已發布。正式 SQL 0 次、正式資料寫入 0 次、GitHub 提交 0 次。本次核對時 GitHub main 為 5c9bf95c23744d74d214b5cd9451c5b356f047aa / v1.13.7；正式 purchase_code 欄位仍不存在。

## 唯讀正式資料檢核

- purchases 264 筆、purchase_payments 284 筆、session_usages 2842 筆；非本次處理或修改筆數。
- 購課日期無缺漏、created_at 無缺漏。正式 purchases 無自訂觸發器，歷史回填不會連帶觸發既有購課更新函式。
- 張淑美運動訓練全域排序為 20261008-002；教練可見子集合重新排序造成舊畫面顯示 001。運動恢復是另一筆合法購課，不刪除。
- 原 purchase_read / insert / update 政策不修改；固定編號不能透過擴大讀取他人資料達成。

## 隔離驗證

- Python 正式範圍回歸 140 項：固定編號、專案查詢/介面、備份 Excel、銷課查詢、未稅付款分配、購課及後續付款、管理員中止表單。
- PostgreSQL/PGlite 固定編號＋原子購課 45 項：完整歷史回填、所有原欄位一致、安全重跑、RLS 子集合固定 002、修改日期/教練不變、UUID/編號禁止修改、刪除不重用、20 筆同日佇列請求唯一編號、超過 999 的序號、有效員工新增、無配號表或函式 API 權限、跨教練新增拒絕與配號回滾、伺服器匯入管理員限制、購課/首期付款任一步失敗全回滾。
- 原 v1.13.7 專案授課教練 RLS 隔離回歸 16 項。
- 共 201 項功能/規則/SQL 隔離檢核。另完成根目錄及正式發布快照 app.py 語法檢查、VERSION 一致性、AST 業務函式一致性核對。
- 唯一函式差異為 daily_page：根目錄仍保留暫停的活動原型；正式快照刻意排除，不覆蓋或刪除使用者原型。
- 測試只使用虛構資料及隔離記憶體資料庫；沒有建立正式測試購課或付款。

## 安全與驗證界線

已取得正式 Supabase security advisors 基線；尚無正式 DDL，所以沒有聲稱完成升級後 advisors。私人 schema、配號表 RLS、撤除直接函式呼叫、固定 search_path、有效 auth.uid/員工角色以及服務端管理員建立者限制均在隔離測試核對。正式執行後仍須重跑 advisors 並與基線比較。

PGlite 0.5.8 / PostgreSQL 18.3 使用單引擎序列處理；20 個 Promise 佇列測試僅證明配號結果唯一，不是兩個獨立 PostgreSQL 連線互相等待的併發實測。跨連線驗收需 staging；原子配號使用 PostgreSQL INSERT ON CONFLICT 的列鎖，而非 client 端 count+1。[PostgreSQL INSERT 文件](https://www.postgresql.org/docs/current/sql-insert.html)、[Supabase 函式安全文件](https://supabase.com/docs/guides/database/functions)。

Supabase CLI 不在目前環境；依使用者既有版本化 SQL 規範建立 flat migration，正式升級將使用既有 MCP migration 管理機制，而不是安裝或猜測 CLI 指令。

本機未啟動測試網站，保留使用者「測試先不使用」選擇。正式 SQL、提交、線上重新部署、管理員/教練真實登入驗收仍待授權及執行。

## 正式 SQL 執行（使用者授權後）

- 2026-10-12：purchase_code_v1_13_8 migration 成功，版本 20261012021509。
- 升級前專用資料快照於 UTC 02:13:16 保存於使用者本機，涵蓋購課/付款/銷課全欄位、映射、欄位/約束/RLS/關鍵函式定義；不是完整 Supabase/Auth/Storage 備份。私人資料不提交 GitHub。
- 升級前後購課 264 筆、付款 284 筆、銷課 2842 筆一致；各表完整原欄位 MD5、購課/付款/銷課金額及銷課未稅合計一致。僅新增固定編號，不重建付款或銷課。
- 264 筆固定編號逐筆符合升級前全域映射，空值與重複各 0；原 RLS 政策、原子購課/付款驗證/銷課函式本文未變。
- 真實 authenticated / smc009 RLS 唯讀查詢確認運動訓練固定 20261008-002，與全域管理員結果一致；運動恢復為 001。沒有建立正式測試交易。
- 私人 schema 的 API 角色無 USAGE、表修改或函式 EXECUTE，兩表 RLS 保持啟用。
- 升級後 advisors 的既有 WARN 不增加：anon SECURITY DEFINER 可執行警示 11 個、authenticated 13 個、外洩密碼保護未啟用 1 個。另新增兩筆 INFO（RLS enabled no policy）：私人配號表刻意無用戶政策，預設拒絕所有用戶；加上無 schema/table/function API 授權，並非新開放權限。[INFO 說明](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)。
- GitHub 以 main v1.13.7 的完整正式樹為基底，只更新本版本程式/文件/測試/SQL，不上傳私人備份、套件快取或活動原型。線上重部署及登入頁驗證將另保存本機 RELEASE_STATUS_v1.13.8.md。
