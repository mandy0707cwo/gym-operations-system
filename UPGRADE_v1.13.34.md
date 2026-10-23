# v1.13.34 升級說明（本機候選）

本版無新增SQL、無資料轉換。從v33更新完整Python來源即可；若正式仍為v31，須先依v32／v33升級說明處理前置SQL，不可只更新畫面。

本機：python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8516 --server.headless true。

驗證：python verify_schedule_display_v34.py。本次顯示調整只執行離線虛構資料回歸，不以v33資料庫測試結果冒充本版重新測試。

核對請假選單無UUID，選擇不同紀錄仍依ID帶入、作廢正確對象；班別人數明細顯示實際上班時段及請假。僅改標籤，不改人數與額度。不改線上環境；復原可回到v33來源，資料無需回滾。
