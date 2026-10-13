# v1.13.10 驗證紀錄

日期：2026-10-13（Asia/Taipei）。
狀態：正式 SQL、GitHub 提交及 Streamlit 重啟均完成；登入頁正常。真實管理員／教練的業務操作仍待登入驗收。

## 結果

| 檢核 | 結果 |
|---|---|
| Python 語法 | app.py、course_defaults.py、正式 app.py 及新測試通過 |
| 正式範圍 Python 回歸 | 162 項通過，tests/verify_v1_13_10.py |
| 新增課程預設 SQL | 18 項隔離 PGlite 檢核通過 |
| 固定購課編號與原子購課／首期付款 | 45 項隔離檢核通過 |
| 教練專案讀取 | 16 項隔離檢核通過 |
| 合計 | 241 項通過，正式資料寫入 0 |

新功能涵蓋：三欄可留白、正數／整數／金額界限、非有限值拒絕、客戶及課程備註分行保留、空來源留白、切換課程清空、一般重跑保留人工修改、購課快照保存與首期金額一致、成功後清空、後續目錄異動不改舊成交、目錄維護 admin guard、欄位不存在時顯示升級提示、SQL 重跑不清除設定、原資料／RLS 不變。

首次平行執行 UI 測試時，冷啟動遇到一項 20 秒測試逾時；未放寬測試時限，改以完整回歸順序重跑，162 項全數通過。沒有忽略失敗或宣稱逾時測試通過。

## SQL 前唯讀資料庫檢查

- course_catalog 目前 6 筆，原 7 欄；新三欄尚未建立，未自行猜測任何堂數、價格或備註。
- 原資料指紋：6a74105eaea43b3bf04fd1647ad31428。正式執行前須重新備份與核對；若使用者期間有修改，以執行當下備份為準。
- RLS 開啟；authenticated 讀取，INSERT／UPDATE／DELETE 以既有 is_admin() 限制。
- 只讀取 schema、政策、筆數與資料指紋，沒有讀取會員個资明細，沒有修改課程或交易。
- 正式 app.py 以 GitHub main ee6a5ff08f18925c10513f0dd1c5347eb6fde77b 為基準；本機暫停活動原型仍保留但不發布。
- 正式快照與根目錄的修改函式一致；daily_page 保持前版正式函式。
- 未更動 requirements.txt 或既有已執行 migration；新欄位使用 numeric 金額、可空白、冪等 CHECK，不擴大既有資料庫權限。
- Supabase／Postgres 規範採 nullable 欄位，沒有 DEFAULT 0，避免把未設定誤認為實際金額；Streamlit 規範在表單建立前帶入 state，避免改值時錯誤或一般重跑覆蓋人工修改。

## 安全 Advisor 基準

這些為既有正式環境提醒，與前版相同，本次未新增或修改這些函式／Auth 設定，不宣稱已修復：
- anon 可執行 SECURITY DEFINER：11 項。[官方檢核說明](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
- authenticated 可執行 SECURITY DEFINER：13 項。[官方檢核說明](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)
- 洩漏密碼保護未啟用：1 項。[官方說明](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)
- 私有 purchase_identity 的 RLS 無用戶政策：2 項 INFO，原設計為禁止用戶直接存取，不為消除提示而開放政策。

## 限制

- 正式 SQL 已經使用者授權執行；真實管理員／教練業務操作仍待登入驗收，不能以本機測試推論已完成業務驗收。
- UI 測試使用虛構資料與模擬 RPC，沒有正式成交。
- PGlite 為隔離單引擎；此版 catalog 權限測試使用測試角色開關模擬既有 is_admin 政策，並非正式 JWT 身分驗證或跨連線併發驗收。
- 本次沒有啟動本機網站或發布暫停活動方案；正式發布需先 SQL、後程式，見 UPGRADE_v1.13.10.md。

## 正式 SQL 執行核對（2026-10-13）

- Migration course_purchase_defaults_v1_13_10，版本 20261013150637，已成功執行，僅新增三欄及 CHECK。
- 6 個原課程的原 7 欄完整資料指紋不變；新欄位全部 NULL，沒有猜測或回填堂數／價格／備註。
- 購課、付款、銷課的資料筆數、金額合計及完整欄位指紋與 SQL 前備份一致；沒有建立正式測試交易。
- course_catalog 原 RLS、四項政策及 grants 完全不變；新 nullable 欄位型別與 CHECK 已核對。
- 安全 Advisor 與 SQL 前基準一致，未新增任何 SECURITY DEFINER 或擴大權限。
- 私人備份位於專案 Git 倉庫之外的工作區 output/private_course_catalog_backup_20261013_v1.13.10.json，含課程原資料、schema／RLS／grants 及交易資料指紋；不是全庫 dump，不發布。

## 線上發布結果

- 程式提交：82a522a4375a3166abf0600a366686b820de3073，main；16 個預期發布檔案，沒有暫停活動原型或私人備份。
- 遠端 app.py 與 course_defaults.py 與本機已驗證的正式快照逐字一致。
- Streamlit Reboot 完成；啟動 UTC 2026-10-13 15:13:47.180，即 Asia/Taipei 2026-10-13 23:13:47.180。
- Python 3.12.15、Streamlit 1.62.0 安裝成功；平台自動將 pyarrow 25.0.1 替換為 24.0.0，requirements.txt 未改動。
- 登入頁正常，未見程式執行錯誤；啟動後有既有 components.v1／use_container_width 棄用提醒，並非本次啟動失敗，本次未進行全系統介面重構。
- 未取得營運系統登入憑證，未建立正式購課或首期付款測試；登入頁正常不等同於真人業務驗收。
- 本機截圖：output/DEPLOY_v1.13.10_20261013_server.jpg、output/DEPLOY_v1.13.10_20261013_login.jpg。
