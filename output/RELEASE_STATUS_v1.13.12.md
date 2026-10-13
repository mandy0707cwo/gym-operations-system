# v1.13.12 線上發布紀錄

日期：2026-10-14（Asia/Taipei）

## 執行結果

- 任務狀態：GitHub main 已提交，Streamlit 已更新並完成一次重啟；登入頁正常。
- 程式提交：c8b46b90a8bcf4bb53e9b986f8e660f3ed33c642。
- 前版：5bde4cb3266a46f5affdfe6967e82a2c47b990f5；版本 v1.13.11。
- 本版：v1.13.12；正式 app.py、ui_text.py、VERSION 已逐檔比對遠端內容一致。
- 程式提交含12個變更檔案；後續另提交發布紀錄與文件狀態，不修改程式。
- 平台顯示[16:55:29] Updated app!，其後完整重新啟動。
- 啟動：2026-10-13 16:56:08.740 UTC；臺灣2026-10-14 00:56:08.740。
- 啟動記錄：Uvicorn server started on :::8501；Python3.12.15、Streamlit1.62.0。
- 本機181項隔離回歸單次通過（235.322秒）；部署前語法再檢核通過。
- 正式資料寫入0筆；未執行SQL、改動資料庫、權限、帳務、查詢或下載邏輯。
- 假設：無新增財務數值或商業條件。

## 變更及限制

- 主功能同名標題保留原大小；45處頁內標題改為Streamlit原生small字級，與分頁標籤同為theme.fontSizes.sm。
- 使用Streamlit技能的原生文字規範；不新增全域CSS、字型或主題修改。
- navigation_platforms.py保持Git blob 38091a8d2e422142cd75dceab2a7fd1254e58740；依賴與既有其他模組不變。
- 正式app.py SHA256：506e20d26a5d1cdf58a1ccf432753e7910e7108ebe7cac72d4364450d9258742。
- ui_text.py SHA256：786b997053c7ea7af7c5ddcc6129594ebe818cd50c7172e77ebddbc1d99b7b68。
- 暫停原型留存本機，不發布線上。
- 未以正式帳號登入業務畫面；此紀錄確認部署、服務啟動及登入頁。內部字級仍請使用者登入後確認。
- 本機pandas3.0.5與正式requirements的pandas2.3.1不同；本機測試不等同正式財務驗收。
- 既有components.v1.html及use_container_width淘汰警告需後續技術維護，非本次新增錯誤。

## 檔案與使用方式

1. output/DEPLOY_v1.13.12_20261014_login.jpg：正常登入頁。
2. output/DEPLOY_v1.13.12_20261014_server.jpg：啟動記錄。
3. output/release_v1.13.12/：正式變更快照，不是完整離線安裝包。

截圖只留本機，不上傳GitHub。重新整理網站並登入，檢查財務平台等主標題與頁內小字；無需SQL或重匯資料。復原見UPGRADE_v1.13.12.md。
