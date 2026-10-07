# v1.13.7 專案代登讀取權限修正

## 範圍

只調整 public.project_entries 的 SELECT 政策。允許有效一般教練讀取本人授課的管理員代登記錄；保留原建立者及主管、共用教練、管理員權限。不更動原始交易或寫入權限。

## 升級

1. 保留原政策與版本備份；確認執行在正式 Supabase 專案。
2. 執行 migration_project_coach_read_v1_13_7.sql。此政策可重跑，既有表與政策必須存在；缺少時停止，不自行建立寬鬆替代政策。
3. 以授課教練帳號重新整理每日營運專案列表，再查詢涵蓋執行日期的營運時數。
4. 驗證管理員代登可見、其他教練隔離、主管與管理員讀取不變，以及記錄筆數、金額、時數與內容指紋不變。
5. SQL 修正立即生效，無須 Reboot。App 顯示版本更新可獨立發布，不應為此中斷營運。

## 復原

如需回復舊讀取規則，由管理員執行下列 SQL；這會讓代登的本人授課記錄再次不可見，不影響資料保存：

```sql
alter policy project_entries_read on public.project_entries
  to authenticated using (created_by=auth.uid() or public.is_manager());
```

不得以關閉 RLS、改寫 created_by、重建記錄或給教練管理員權限代替修正。

## 本機測試

```powershell
node tests/test_project_coach_read.mjs
python -m unittest discover -s tests -p "test_*.py"
```

隔離 PostgreSQL 測試沿用 output/qa_atomic_runtime 中的 PGlite；也可用 PGLITE_RUNTIME 指向已安裝的 @electric-sql/pglite/dist/index.js。不連正式資料庫、不建立正式測試交易。
