# v1.13.10 發布紀錄

- 日期：2026-10-13（Asia/Taipei）。
- 使用者已同意正式 SQL、提交及線上更新。
- 發布前 main：ee6a5ff08f18925c10513f0dd1c5347eb6fde77b，v1.13.9。
- 已備份 6 筆課程目錄、schema／RLS／grants 及交易資料指紋；私人備份僅存本機工作區，非全庫 dump，不發布。
- SQL course_purchase_defaults_v1_13_10（20261013150637）已完成；6 個課程原 7 欄完整資料、RLS／grants／政策與購課、付款、銷課的完整資料指紋皆不變。
- 三個新增欄位 default_sessions、default_total_amount、note 全為 NULL，未填入價格或堂數。
- 241 項本機／隔離檢核通過；現有安全 Advisor 基準不變，未擴大權限。
- 程式提交與線上啟動仍在處理，完成後補登；不發布暫停活動原型或私人備份。
