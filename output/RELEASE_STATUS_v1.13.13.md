# v1.13.13 線上發布紀錄

日期：2026-10-14（Asia/Taipei）。

## 執行結果

- 已提交GitHub main並部署Streamlit，完整重新啟動一次；登入頁正常。
- 程式提交：a0dfee10a4252181404624829905627365c3b921；前版main：a6d22f272b515693e816cf56ec339aa8eab9482d。
- 版本v1.13.13，程式提交15個變更檔案；app.py、confirmed_queries.py與VERSION逐檔核對遠端一致。
- 啟動：2026-10-14 14:42:08.673 UTC；臺灣2026-10-14 22:42:08.673（Asia/Taipei）。
- 平台：Starting up main / app.py、Pulling code changes、Uvicorn server started on :::8501。
- Python3.12.15、Streamlit1.62.0；requirements、ui_text.py與navigation_platforms.py遠端Git blob和前版相同。
- 完整193項隔離回歸通過（329.847秒）；最後分期選取修正後，相關41項再次通過（70.875秒），共覆蓋194項不同檢核。不是最終194項同次執行。
- 獨立唯讀發布稽核通過：版本、hash、私有快照、會員／ID交集、分期選取對應、53個未變函式及7個寫入／RPC一致性；正式版無暫停原型。
- 正式資料寫入0筆，未執行SQL、變更資料庫／RLS／權限／機密設定／帳務公式或重匯資料。

## 變更與範圍

- 成交總表第三分頁會員查詢：會員及購買_ID可單獨或交集，最新查詢截至查詢當日；原日期區間及截止日期保留。
- 實際預收收入更名預收款項，分頁、提示與Excel檔名／工作表同步。
- 具查詢按鈕頁面先確認才讀取結果；主檔下拉可以先載入。主要搜尋／財務結果使用私有快照，改條件需重新查詢。
- 客戶查詢後選取的購課摘要、付款歷史及寫入前安全檢查仍即時讀取，不宣稱所有rerun皆零交易讀取。
- 依Streamlit指引同次發布app.py及confirmed_queries.py，不新增全域CSS或主題設定。
- app.py SHA256：cfb15108831de397f3d0faeb75dd3d86bbac68bb989598e4e8bee293ca62c191。
- confirmed_queries.py SHA256：a837f9aa6a3a378b9c2f62931b8b5d117b483d422ca6d37b24b52c356f2a44f0。

## 證據與使用

1. output/DEPLOY_v1.13.13_20261014_login.jpg：重啟後正常登入頁。
2. output/DEPLOY_v1.13.13_20261014_server.jpg：最新啟動記錄。
3. output/release_v1.13.13/：正式變更集合，不是完整離線安裝包。

截圖留本機，不上傳GitHub。重新整理並登入，至財務平台 → 各項查詢 → 成交總表 → 會員查詢，輸入會員或購買_ID後按查詢，確認表格、總計與下載。

## 限制及復原

未使用正式帳號登入業務畫面，實際查詢結果及帳務仍待使用者確認。沒有新增財務數字或商業條件假設。復原僅還原v1.13.12正式程式、版本及文件，不清除或回滾營運資料；見UPGRADE_v1.13.13.md。
