# v1.13.29 驗證紀錄（2026-10-22）

- 離線規則及AppTest 103項，101通過、2項既有歷史快照比較略過。涵蓋四列、唯一分組、原班別保留、半日休A／B／歧義C、其他待確認、無查詢控制、原查詢狀態忽略、明細點選同步、例假按班別上色及資料不回寫。
- 主管與管理員同分頁、主管額度確認、本人教練拒絕、兩管理角色下載入口一致及既有審核／請假／防重送測試已涵蓋。
- 資料庫測試56項全部通過。使用v29新建的獨立127.0.0.1:55439虛構庫，不重用正式連線。先套用全部前置SQL，再將新migration套用兩次，核對業務資料筆數未改。詳細結果在verification_schedule_database.json，僅成功才可打包。
- 真實SQL測試包含主管可確認額度、重送回傳原結果、主管可讀額度稽核、教練／匿名／停用拒絕與直接資料表寫入拒絕，並回歸原排班、請假、購課及銷課交易測試。
- 初次新庫回歸發現舊測試假設預設班別已存在，已修正為同時支援空結果的回滾比較，再完整重跑；不是略過失敗。例假AppTest的預期文字同步改為新底色標記。
- audit_scheduling.py檢查八表RLS、無直接DML、七個公開INVOKER門面、匿名不得執行、私有收據及主管額度guard／稽核policy。audit_shift_counts_v29.py另核對財務、正式repository與舊migration未變。
- AppTest不執行CCv2 JavaScript；實際瀏覽器另核對班別人數四列、無查詢欄位、半日休C班明細及例假底色。截圖置於同版本output資料夾。

執行：`python verify_scheduling.py`、`python verify_scheduling.py --database`、`python audit_scheduling.py`、`python audit_shift_counts_v29.py`。資料庫驗證僅可在專用虛構庫執行。
