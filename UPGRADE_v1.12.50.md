# v1.12.50 升級說明

## 目的

將銷課未稅入帳改為：整筆課程未稅總額為準，非最後一堂使用固定未稅金額，最後一堂吸收全部四捨五入尾差。

## 執行前

1. 先下載完整資料備份，並保留 Supabase 資料庫備份。
2. 確認已執行 `migration_usage_net_amount_v1_12_42.sql`，`session_usages` 已有 `deducted_net_amount`。
3. 更新期間暫停新增銷課，避免函式切換當下仍有使用者寫入。

## 執行步驟

1. 開啟正確的 Supabase Project。
2. 進入 SQL Editor。
3. 貼上並執行 `migration_usage_final_session_rounding_v1_12_50.sql` 全文。
4. 第一個驗證查詢應顯示 `Success. No rows returned`；若有資料，先不要修改，請保留結果供檢查。
5. 第二個驗證查詢應顯示新版 `consume_session` 函式內容。
6. 將 Streamlit Secrets 的 `APP_VERSION` 更新為 `v1.12.50`。
7. SQL 成功後，再部署 v1.12.50 App。

## 計算範例

含稅成交總額 $20,280、12 堂：

- 整筆未稅總額：`round(20,280 ÷ 1.05) = 19,314`
- 第 1～11 堂：每堂 `round((20,280 ÷ 12) ÷ 1.05) = 1,610`
- 第 12 堂：`19,314 - (1,610 × 11) = 1,604`
- 未稅明細合計：`19,314`

## 歷史資料影響

- Migration 不更新、不刪除任何既有銷課紀錄。
- 已完成課程維持原先固定保存的未稅入帳值。
- 尚未完成課程的既有未稅金額保持不變；後續一般堂次使用新固定算法，最後一堂會以整筆未稅總額扣除先前已入帳金額後補足尾差。

## 復原方式

如需回復舊算法，可重新執行 v1.12.42 migration 中的 `consume_session` 函式定義；不要刪除 `deducted_net_amount` 欄位，也不要覆寫既有銷課資料。
