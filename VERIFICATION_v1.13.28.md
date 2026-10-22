# v1.13.28 驗證紀錄（2026-10-22）

- 本輪離線規則與AppTest共96項，94通過、2項既有歷史快照比較略過，零失敗／錯誤；詳verification_schedule_ui.json。未把略過當成通過。
- 新增9項測試：0/2、1/2、2/2；部分不在班與指定時段；重複／相鄰／重疊區間；邊界與非法輸入；C班／半日休／缺時段；核准及資料完整性；前端安全資料與查詢條件驗證；移除文字及選項但保留歷史。
- AppTest不執行瀏覽器JavaScript；新元件事件在AppTest使用受控替身。另以實際瀏覽器驗證真實CCv2點選：10/1 A班0/2，點擊取得兩位虛構教練「整個班段不在班」；10/5 A班2/2＊，點擊看到09:00–13:00、16:00–18:00剩餘時間，無私人請假原因。
- 實際瀏覽器已核對日期／星期上下列、分組、合計、水平捲動及明細。畫面留存於同版本output資料夾。
- 核對59個既有app函式語法樹未變；財務及資料庫核心檔案另由audit_headcount_release.py逐檔與v27比對。
- 本輪未重跑資料庫測試。verification_schedule_database.json及verification_schedule_security.json仍明確標示v1.13.27，僅保留前版證據，不作v28新驗證。沒有SQL或資料庫權限變動；不能因此聲稱已完成本版正式環境驗證。

執行：`python verify_scheduling.py`；稽核：`python audit_headcount_release.py`；打包：`python package_scheduling_v28.py`。
