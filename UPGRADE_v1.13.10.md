# v1.13.10 課程購買預設升級

日期：2026-10-13（Asia/Taipei）。
狀態：正式 SQL 已完成，程式已提交並更新線上；2026-10-13 台北 23:13:47.180 啟動，登入頁正常。原資料與權限核對不變，操作驗收待管理員登入。詳見 output/RELEASE_STATUS_v1.13.10.md。

## 使用方式

1. 系統管理員開啟資料管理 → 課程名稱管理 → 新增或修改。
2. 課程堂數、成交總金額、備註均為選填；未設定請留白，不用 0 表示空白。成交總金額是含稅課程總額，不是每堂單價。
3. 購課人員在購買及分期 → 課程購買選擇課程，有值才帶入，未設定空白，帶入後仍可修改。
4. 客戶備註在前、課程備註在後，分行保留；只有一方有值就帶入該方，皆無資料時留白。
5. 切換課程重新帶入或清空；一般重跑、驗證失敗或資料庫失敗保留人工修改。
6. 只在購課＋首期付款成功確認後清空；不修改既有成交內容。

## 正式升級順序（需使用者同意）

1. 確認 Supabase 專案 qrtniwxlexvbjoeyjxwv，先備份 course_catalog 原資料、schema／RLS，保留既有交易備份。
2. 執行 migration_course_purchase_defaults_v1_13_10.sql；不要重跑 database.sql 重建正式系統。
3. 核對既有 6 個課程及原 7 欄完整資料不變，新三欄全為 NULL；RLS、政策及既有交易筆數與金額不變。
4. 使用 output/release_v1.13.10/app.py、course_defaults.py 及同資料夾正式 Markdown 發布；VERSION、migration、測試及升級／驗證文件同步。不發布根目錄暫停活動原型或私人備份。
5. 重啟線上服務並驗收管理員新增／修改、選課帶入、留白、清空、合併備註。不要為驗收建立正式購課交易。
6. 既有課程的新三欄不自動推定價格或堂數，須由管理員逐一填入正確設定。

## 安全與復原

- 僅新增三個 nullable 欄位、CHECK 與註解，不含資料 INSERT／UPDATE／DELETE、GRANT 或政策變更。
- 5 秒鎖定逾時、30 秒執行逾時；無法取得鎖時會失敗回滾，不強制終止其他交易。
- 可安全重跑，已填設定不清空。若復原舊程式，保留新增欄位即可，勿刪除已填預設。
- 課程備註沿用 authenticated 目錄讀取權限，會給購課人員帶入，不應存管理員限定機密。
- 原子購課＋付款、未稅尾差、時數、獎金、退款公式與固定購買編號均不變。
- Supabase CLI 未安裝，依專案既有版本化 SQL 命名慣例準備 migration；已由 Supabase 工具完成並登錄 course_purchase_defaults_v1_13_10（20261013150637）。

## 本機測試命令

在專案目錄與 requirements.txt 環境執行：

```powershell
python -m py_compile app.py course_defaults.py output/release_v1.13.10/app.py
python tests/verify_v1_13_10.py
node tests/test_course_defaults.mjs
node tests/test_purchase_codes.mjs
node tests/test_project_coach_read.mjs
```

Node 資料庫測試需 PGlite，使用既有 output/qa_atomic_runtime，或設定 PGLITE_RUNTIME 指向已安裝套件的 dist/index.js。所有測試使用虛構資料，不連正式 Supabase。
