# 專案維護規則

對本專案進行任何修改時，必須遵守：

1. 每次修改建立新版本，不得沿用已發布版本號。
2. 同步更新 VERSION、app.py 預設顯示版本及 CHANGELOG.md。
3. 功能、權限、計算或操作流程變更時，更新 SYSTEM_DOCUMENTATION.md。
4. 資料表、欄位、關聯或報表資料來源變更時，更新資料字典.md。
5. 部署方式變更時，更新 README.md 或 LOCAL_DEPLOYMENT.md。
6. 資料庫變更建立新的版本化 migration SQL，不得修改已執行的舊 migration。
7. 人工升級步驟建立 UPGRADE_vX.Y.Z.md。
8. 完成前核對版本、語法、測試、權限、資料筆數與財務合計。
9. 金鑰、密碼、token 及 Supabase secret key 不得寫入程式或 Markdown。

版本與發布檢核依 VERSIONING.md 執行。
