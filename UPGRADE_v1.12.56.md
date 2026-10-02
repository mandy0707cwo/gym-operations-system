# v1.12.56 升級說明

1. 升級前先下載完整資料備份。
2. 在 Supabase SQL Editor 執行 `migration_customer_full_access_delete_v1_12_56.sql`。
3. 確認顯示 `v1.12.56 客戶完整查詢修改與安全刪除權限建立完成`。
4. 部署本版本程式，並將 Streamlit Secrets 的 `APP_VERSION` 更新為 `v1.12.56`。
5. 驗收：
   - 一般教練可新增、查詢及修改全部客戶。
   - 一般教練看不到刪除功能。
   - 系統管理員可刪除沒有購課及銷課紀錄的客戶。
   - 有購課或銷課紀錄的客戶會被阻擋刪除。
   - 預收收入同時顯示「付款期次」與「分期狀態」，且分期狀態與成交總表一致。

復原方式：重新套用 v1.12.21／v1.12.26 的客戶 RLS 條件，並將 `member_change_logs.member_id` 外鍵改回 `on delete restrict`；程式則回復上一版本。
