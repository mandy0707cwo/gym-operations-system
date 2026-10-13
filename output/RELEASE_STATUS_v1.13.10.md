# v1.13.10 發布紀錄

- 日期：2026-10-13（Asia/Taipei）。使用者已同意正式 SQL、提交及線上更新。
- 發布前 main：ee6a5ff08f18925c10513f0dd1c5347eb6fde77b，v1.13.9。
- 程式提交：[82a522a4375a3166abf0600a366686b820de3073](https://github.com/mandy0707cwo/gym-operations-system/commit/82a522a4375a3166abf0600a366686b820de3073)，16 個預期檔案。
- SQL course_purchase_defaults_v1_13_10（20261013150637）已完成；6 個原課程的原 7 欄完整資料、RLS／grants／政策不變。
- 購課 264 筆、付款 284 筆、銷課 2878 筆的金額與完整資料指紋皆與 SQL 前一致；沒有建立正式測試交易。
- 三個新增欄位 default_sessions、default_total_amount、note 全為 NULL，沒有推定或填入堂數與價格。
- 已備份課程目錄及 schema／RLS／grants、交易資料指紋；檔案只留本機工作區 Git 倉庫之外，不是全庫 dump，不發布。
- 241 項本機／隔離檢核通過；現有安全 Advisor 基準不變。
- app.py 與 course_defaults.py 已提交並核對與正式快照一致；不包含暫停活動原型或私人備份。
- Streamlit 已 Reboot；啟動 UTC 2026-10-13 15:13:47.180／台北 2026-10-13 23:13:47.180。
- Python 3.12.15、Streamlit 1.62.0；平台自動將 pyarrow 25.0.1 替換為 24.0.0，專案依賴檔未改動。
- 登入頁正常，未見程式執行錯誤；有既有介面棄用提醒，本次未進行不相關全系統重構。
- 證據只存本機：output/DEPLOY_v1.13.10_20261013_server.jpg、output/DEPLOY_v1.13.10_20261013_login.jpg。
- 使用者登入後，先於資料管理 → 課程名稱管理填寫三項預設，再驗收購買及分期 → 課程購買的帶入、留白、合併備註及手動調整。
- 限制：尚未用正式管理員／教練帳號完成業務操作驗收，不把登入頁正常視為全部功能已真人驗收。
