# v1.13.8 正式發布與部署結果

## 執行結果

- 狀態：2026-10-12 正式 SQL、GitHub main 更新及 Streamlit 重啟完成，登入頁正常，未顯示腳本執行錯誤。
- 程式提交：[f75a0f42e373c6d9e33de3ea3ca776fdf648af9a](https://github.com/mandy0707cwo/gym-operations-system/commit/f75a0f42e373c6d9e33de3ea3ca776fdf648af9a)，父提交 5c9bf95c23744d74d214b5cd9451c5b356f047aa，非強制更新。後續部署文件提交不改變程式版本。
- Supabase migration：purchase_code_v1_13_8，版本 20261012021509。
- 固定編號回填 264 筆，逐筆與升級前全域管理員映射一致；無空值/重複。
- 升級前後購課 264 筆、付款 284 筆、銷課 2842 筆；原欄位 MD5、金額及銷課未稅合計全部一致。不重建或刪除交易。
- 原 RLS 政策及 create_purchase_with_first_payment、validate_purchase_payment、consume_session 函式本文未變。私人配號 schema/table/function 對 API 角色無直接存取權。
- 使用實際教練 authenticated RLS 查詢確認問題購課固定編號與全域管理員結果一致。會員識別資訊留在私人檢核，不放於公開部署文件。
- 隔離檢核：Python 140 項、固定配號與原子購課 PostgreSQL 45 項、專案 RLS 16 項，共 201 項通過；正式 app.py 語法通過。
- GitHub main 的 app.py、VERSION 及 migration 與正式發布檔逐字一致。只移植本次改動；既有線上文件歷史完整保留，不上傳活動原型、私人交易備份或套件快取。
- Streamlit 日誌：UTC 2026-10-12 02:22:38.699 Uvicorn server started（台北 10:22:38.699）；重新克隆 main 後登入頁正常。
- 平台初次套件下載遇 pyjwt 網路 broken pipe，改用標準 pip 後成功；平台自動將已知有問題的 pyarrow 25.0.1 換為 24.0.0。沒有擅自更新 requirements。

## 檔案與使用

- [線上入口](https://gym-operations-system-ccdwjvfve92h3kdlvevoj7.streamlit.app/)：重新整理或重新登入後，再執行查詢，勿沿用旧搜尋結果。
- 升級：UPGRADE_v1.13.8.md；驗證：VERIFICATION_v1.13.8.md；正式快照：output/release_v1.13.8/app.py。
- 本機部署證明：output/DEPLOY_v1.13.8_20261012_server.jpg、output/DEPLOY_v1.13.8_20261012_login.jpg。
- 升級前交易快照及升級後配號表快照僅存於本機工作區 output 目錄，不提交 GitHub。涵蓋本次受影響交易及配號資料，不是完整 Supabase/Auth/Storage 備份；後續完整 DB 備份應包含私人 purchase_identity schema。

## 驗收界線

- 未取得應用程式帳號密碼；未登入真實教練/管理員介面，沒有在正式資料庫建立測試購課或付款。登入頁正常不等於所有正式交易已人工驗收。
- 獨立 PostgreSQL 連線併發實測仍需 staging；單引擎佇列測試不宣稱多連線併發。
- advisors 既有 WARN 未增加。兩筆新的 RLS-no-policy INFO 是私人配號表預設拒絕用戶、配合撤除所有直接 API 權限的結果，不是開放用戶存取。
- Streamlit 規範影響：以正式來源快照部署，保留暫停的本機原型；Supabase 規範影響：先備份、保留 RLS、受限私人配號函式，並核對映射、原欄位及安全顧問。

