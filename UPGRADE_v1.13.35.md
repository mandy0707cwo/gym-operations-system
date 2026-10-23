# v1.13.35 升級說明（本機候選，未部署）

1. 備份資料庫與原版程式。正式仍為v31時，先依v32／v33說明升級；已完成的前置migration不可重跑。
2. 執行supabase/migrations/20261023143211_schedule_quota_draft_v1_13_35.sql，確認私有assert_quota沒有authenticated execute授權，舊command的角色／版本／收據檢查保留。migration可重跑，版本不符會停止。
3. 部署完整v35來源；未核定額度的月份教練將無法編輯，主管應先核定。既有草稿或超額資料不刪除，已確認月份不解鎖。額度降低後超額須調整才可由教練保存。
4. 測試未核定停用、草稿半月可保存、達額可保存、超額不可保存與送出、整月送出後鎖定、主管更正、防重送與併發版本拒絕。核對財務及歷史資料未變。

本機使用python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8517 --server.headless true，先切換測試主管核定額度。未按草稿的預排重新整理可能遺失。

復原：需一起復原v34來源與舊私有command定義，不能只降版畫面；新寫入班表不應整批覆蓋。資料不刪除、無自動歷史重算。本機驗證只指固定localhost:55439虛構庫，不可改成正式連線。
