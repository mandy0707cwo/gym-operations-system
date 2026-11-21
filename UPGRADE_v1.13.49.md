# v1.13.49 升級說明（本機候選，未發布）

## 前置與範圍

須已有v1.13.48程式、v47中止更正及v18計算中心資料庫。不得對空資料庫只套本migration。目前僅製作本機版，尚未取得正式發布同意。

## 升級順序

1. 完成虛構資料測試及使用者驗收，取得上線同意。建立可復原資料庫備份，保存原程式、函式與部署設定（不含密碼），記錄原交易筆數及財務雜湊。
2. 在隔離資料庫演練 `supabase/migrations/20261121061449_coach_performance_monthly_hours_v1_13_49.sql`。它是一次性新增，遇同名結構即停止，不自動覆蓋。
3. 核准後以正式管理流程套migration，驗證新三張私有表RLS／精確函式簽章。主管與管理員可彙總及登錄工時；教練、共用教練、停用、匿名不行。任何一般登入者不能直接寫表。
4. 依官方清單執行advisors；既有問題另記錄，不盲目放寬權限。發布app.py、operations_ui.py、coach_performance*.py、VERSION及文件，不上傳備份、output、測試依賴或secrets，不整批stage目前髒工作目錄。
5. 確認APP_VERSION設定未覆寫版本，唯讀驗收三分頁與原營運管理／財務報表；不得為驗收任意修改正式工時或交易。核對原交易筆數及財務雜湊不變。
6. 新工時初始空白，由管理者登錄，不猜算歷史工時或從排班匯入。

月工時在私有schema，不包含在原前台Excel備份。完整備份／重建必須包含performance_private的三張表與函式（含原本其他schema）；檢查pg_dump清單不可只選public。此版沒有宣稱前台Excel可還原工時或整套系統。

## 復原

先回復已保存v1.13.48程式，保留新增表中已填工時及稽核；舊版不引用新表，不需要刪表。若要還原整個資料庫須另確認停機與備份後新增交易，不能直接覆蓋。

## 計算決策與操作

月工時與80%目標依使用者確認。缺月、0工時或部分月份不算達成率，不按天分攤。總時數包含四項實際登錄，與含活動、排除動磁波／跨月補單的獎金計時分開，沒有修改獎金計算。

完整公式與資料來源見SYSTEM_DOCUMENTATION.md與資料字典.md。測試執行 `python verify_coach_performance_v49.py`；示範執行 `python -m streamlit run performance_demo.py --server.port 8519`，使用虛構資料，不需要資料庫密碼。

權限設計參考[Supabase官方函式文件](https://supabase.com/docs/guides/database/functions)；保持現有CLI v2.75.0，沒有升級CLI或應用依賴，見[CLI v3異動](https://supabase.com/changelog/supabase-cli-v3)。
