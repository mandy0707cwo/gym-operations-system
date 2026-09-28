# 秀傳運醫營運系統

> 目前版本：v1.12.49。完整說明請參考 [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)，版本規範請參考 [VERSIONING.md](VERSIONING.md)。

# 健身房線上營運管理系統


> v1.12.48：新增僅限系統管理員使用的分期付款更正、補繳與異動紀錄功能。既有系統請先執行 `migration_installment_payment_management_v1_12_48.sql`，並參考 `UPGRADE_v1.12.48.md` 完成驗收。


以 Streamlit + Supabase（PostgreSQL / Auth）建立，可供多人以系統帳號與密碼遠端登入。包含每日營運、課程購買與最多三期付款、原子化銷課、主管 Dashboard，以及 admin 帳號與權限管理。


院內Windows本機落地請參考 `LOCAL_DEPLOYMENT.md`。v1.12.0起提供16GB記憶體規格的Docker部署、健康檢查、每日備份與USB備份工具；本機驗收完成前應保留線上系統。


升級至 v1.12.16 時，請先在 Supabase SQL Editor 執行 `migration_usage_makeup_v1_12_16.sql`，再部署新版 App。此更新新增補單與實際銷課日期；兩個日期跨不同年月時，不列入教練執行時數。


系統管理員可在「資料管理 → 資料匯入／匯出 → 一鍵下載備份」下載完整Excel資料備份。檔案保留資料庫UUID與關聯欄位，但基於安全限制不包含登入密碼、API金鑰及Streamlit Secrets；此功能不能取代Supabase資料庫層級備份。


## 一、建立資料庫


1. 到 Supabase 建立新 Project。
2. 開啟 **SQL Editor**，貼上並執行 `database.sql` 全文。
3. 到 **Authentication > Users** 建立第一位使用者（Email / Password）。
