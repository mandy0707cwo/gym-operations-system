# v1.13.8 升級：固定購課編號

## 狀態

正式 SQL 已於 2026-10-12 02:15 UTC 完成，migration 版本 20261012021509；原有資料欄位及金額校驗一致。程式發布/部署依現場驗證紀錄，不能僅由 SQL 完成推論畫面已更新。新程式需要 purchase_code 欄位。

## 執行順序

1. 暫停新增/修改/匯入，建議備份完整 DB。本次已另存三張受影響交易表的完整資料、欄位/約束/RLS/關鍵函式定義，以及升級前全域日期序號與 UUID 映射；這是本次修正的專用資料快照，不是整個 Supabase/Auth/Storage 的完整 DB 備份。不要使用只有報表的 Excel 當完整 DB 備份。
2. 確認 Supabase 專案 qrtniwxlexvbjoeyjxwv，以及既有原子購課 v1.13.6 RPC。
3. 執行 migration_purchase_code_v1_13_8.sql。全交易有鎖與逾時，失敗全部回滾；請勿自行略過中途錯誤繼續。
4. 核對原欄位校驗、付款及銷課筆數/金額未變、編號無空值/重複、私人 schema 未公開且無 API 存取權限。
5. 張淑美 2026-10-08 運動訓練應固定為管理員原有 20261008-002；運動恢復為 001。請以 UUID、會員、課程、教練交叉驗證，不能僅比編號。
6. 發布 output/release_v1.13.8/app.py 及此版本文件、測試/SQL。此正式快照以 GitHub main v1.13.7 為來源，不包含暫停活動原型。
7. 重新部署，清除舊查詢結果、重新登入教練/管理員確認相同編號；核對查詢、後續付款、銷課、下載及備份。部署前舊程式仍會動態編號，SQL 單獨執行不代表畫面已修好。

## 安全與還原

- 不修改 UUID/外鍵、付款、銷課、金額或時數。不刪除兩筆不同課程。
- 新購課與首期付款 RPC 維持同一交易，觸發器自動配號；不使用 count+1。
- 已提交後刪除的編號不重用。失敗交易配號會跟著回滾，不屬於已發編號。
- 既有舊下載檔的教練序號可能指向其他購課。重新匯出並核對 purchase_uuid；以日期編號匯入必須提供 UUID，不自動猜測別名。
- 一般資料匯入不接受自行指定 purchase_code。完整 DB 還原需專業維運以交易還原 public 資料與私人 purchase_identity 計數器、issued_codes 及觸發器；只還原 public 或刪除私人記錄將破壞不重用規則。
- 回復舊程式會重新出現原顯示問題。不可為回復介面而刪除固定編號或更換 UUID；應修正程式後重部署。資料庫復原使用已驗證完整備份。
- 真正獨立 PostgreSQL 連線的同時交易競爭須於 staging 再驗收；PGlite 單引擎佇列測試不宣稱等於跨連線併發實測。

## 重跑隔離測試

在已安裝 requirements.txt 的 Python 環境中，於專案根目錄執行：

```powershell
New-Item -ItemType Directory -Path output/qa_v1.13.8_temp -Force | Out-Null
$env:TEMP=(Join-Path (Get-Location) 'output/qa_v1.13.8_temp')
$env:TMP=$env:TEMP
python tests/verify_v1_13_8.py
node tests/test_purchase_codes.mjs
node tests/test_project_coach_read.mjs
```

Node SQL 測試需要 @electric-sql/pglite 0.5.8。既有隔離套件在 output/qa_atomic_runtime/node_modules；若路徑不同，可用環境變數 PGLITE_RUNTIME 指向已安裝的 dist/index.js。不需要正式 Supabase 連線或金鑰。
