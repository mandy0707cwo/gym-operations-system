# v1.13.41 年度兩張獨立圖表

- 本機候選版，未發布線上。原v1.13.40來源與套件保留不動。
- 只調整operations_ui.py的年度圖，改為上下兩張，各自標題與座標；不改operations_metrics.py、operations_repository.py或任何SQL／資料。
- 使用`python verify_operations_charts_v41.py`驗證，包含獨立資料序列、表格／日期／角色及既有財務回歸。檢查兩圖數值與年度表一致、沒有將兩指標混成一圖、未來月份不補零。
- 本機展示：`python -m streamlit run operations_demo.py --server.address=127.0.0.1 --server.port=8519 --server.fileWatcherType=none`。只供虛構資料，非正式服務。舊版8518保留，新版使用8519。
- 若需發布，須先取得授權，重新核對遠端版本並完成正式角色只讀驗收；本版沒有資料庫升級。回復只需回到前一已驗證程式版本，不回滾交易。
