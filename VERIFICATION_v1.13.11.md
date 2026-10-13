# v1.13.11 驗證紀錄

日期：2026-10-13（Asia/Taipei）。
狀態：完整隔離驗證完成，使用者已同意提交及部署；本版發布中。沒有啟動本機網站，沒有操作正式資料庫。最終線上結果見 output/RELEASE_STATUS_v1.13.11.md。

## 結果

- app.py、navigation_platforms.py、正式快照及變更測試的 Python 語法檢查通過。
- 發布前整套完整重跑 172 項全部通過（264.831 秒）。先前首輪 168 通過、4 失敗皆為舊選單／版本／daily_page 固定檢核；同步更新後先針對性重跑四項通過，再做本次完整重跑，未忽略失敗。
- 新增 10 項導覽檢核在完整執行中通過：五個每日分頁順序、第一分頁銷課、每個分類只讀自身資料、兩平台分頁順序／切換、各角色入口、未知角色拒絕、非管理員直接進入兩平台拒絕且無資料讀取。
- 57 個前版頂層函式，52 個 AST 完全相同；其餘五個僅每日入口整併、銷課標題、營運總覽標題、每月查詢標題、備份版本顯示變更。獨立抽驗後四個函式除了指定標題／版本外 AST 完全相同。
- 每日執行分類中的 INSERT／RPC 名稱、傳入欄位、金額與時數 payload AST 與前版相同。
- root 與正式快照同名正式函式一致；navigation_platforms.py 兩份相同。已暫停原型僅保留在本機 _paused_daily_pilot_page，正式入口不呼叫、正式快照不包含。
- VERSION 及正式 VERSION 都為 v1.13.11；app 預設備份版本 v1.13.11。未將已執行 v1.13.10 SQL 檔名改成新版本。
- 無資料庫結構／RLS 變更，無 migration，無正式資料寫入。不對正式會員、金額、筆數做未經讀取的驗收宣稱。
- 現有匯入／匯出工作表名稱、帳務公式、尾差、執行時數、獎金、付款與中止流程不變。

## 來源及完整性

- 基準為 GitHub main 的已發布 v1.13.10 app.py；下載內容與本機 output/release_v1.13.10/app.py 完全一致。
- 基準 app.py GitHub blob：42fa9e22adbd352ee4d53e6b18eebee86ea46cf5。
- 新正式 app.py SHA256：75b9a57449d96f9f767cecc1c001d36abe04e6c6ea38fa7ba50342578fcea55c。
- 新 navigation_platforms.py SHA256：4f737bbec8917eadfec7ab856f62b82a79f94638b1ab24f835f7a63bee6d634c。
- 正式快照文件以 GitHub 現行文件增補，不直接公開本機未發布原型或歷史私人診斷資料。

## 測試環境及限制

- Streamlit 1.62.0，與現有依賴相同；本機回歸使用 pandas 3.0.5／openpyxl 3.1.5，正式 requirements.txt 的 pandas 2.3.1 不變。此為隔離邏輯／UI 測試，不替代正式部署相容性與管理員登入驗收。
- AppTest 使用虛構角色、模擬讀取或原有虛構交易測試，不使用正式會員。
- 初次測試碰到沙箱暫存目錄 PermissionError，改在工作區 output/test-temp-v1.13.11 測試；一般 Python 缺 openpyxl，使用既有套件來源，不安裝或更新系統套件。
- 新增分頁測試最初對「沒有操作項目」的專案誤預期查詢明細；依原程式「沒有項目即不查明細」修正測試，未更改正式邏輯。
- 隔離測試程序均已完成。之後的正式重啟由使用者明確同意授權，結果另列發布紀錄。
- 發布後仍須確認伺服器啟動紀錄、原管理員及教練登入、表單／查詢／下載。發布需將 app.py 與 navigation_platforms.py 同一提交。

## 重現

於已有 requirements.txt 套件的專案環境：
```powershell
python -X utf8 -m py_compile app.py navigation_platforms.py
python -X utf8 tests/verify_v1_13_11.py
```

本機版本化正式快照用於比較；這組發布檔案不是包含資料庫與全部依賴的離線安裝備份。
