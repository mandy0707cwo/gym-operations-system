# v1.13.11 正式發布紀錄

狀態：GitHub 提交及 Streamlit 完整重啟完成，登入頁正常；真實管理員／教練業務操作待登入驗收。
程式變更日期：2026-10-13。發布與確認：台北 2026-10-14（Asia/Taipei）。

## 發布資訊

- 專案：mandy0707cwo/gym-operations-system，main，app.py。
- 前版 main：7b3ed9f708e8cfe5a1768ccf8c558a2090de4370，v1.13.10。
- 本次程式提交：72c825714ae97269a18b8a8a419e93e28b2640f7。
- app.py 與 navigation_platforms.py 同一次原子提交；主分支使用前版 SHA 檢查，未強制覆蓋其他提交。
- 13 個變更檔案：程式／選單模組、VERSION、五份說明文件及五份測試／回歸檔案。沒有 SQL、requirements.txt、機密設定或正式資料檔。
- 已核對遠端 app.py／navigation_platforms.py／VERSION 與正式快照一致；requirements.txt 與前版完全一致。
- 正式 app.py SHA256：75b9a57449d96f9f767cecc1c001d36abe04e6c6ea38fa7ba50342578fcea55c。
- 原型不在正式 app.py，不上傳本機含原型的工作檔。

## 部署結果

- 平台日誌：[16:07:49 UTC] 拉取程式，[16:07:51 UTC] Updated app。
- 使用者同意範圍內確認 Reboot，之後完整啟動：
  - UTC：2026-10-13 16:08:45.242。
  - 台北：2026-10-14 00:08:45.242。
- Python 3.12.15、Streamlit 1.62.0；正式 pandas 2.3.1 等依賴保留。
- 平台沿用既有 PyArrow 25.0.1 → 24.0.0 修復，不是本次主動變更 requirements。
- 新登入頁顯示秀傳運醫營運系統、帳號、密碼及登入按鈕；沒有語法或模組匯入錯誤畫面。沒有使用正式業務帳號登入或建立交易。
- 舊版 components.v1／use_container_width 的既有棄用提示不在本次擴大修正範圍。

## 驗證及資料保護

- 完整 172 項本機隔離回歸單次全部通過；沒有忽略先前舊版本測試失敗。
- 角色入口、分頁順序、選取才執行、管理員 guard 及原有業務邏輯已檢核。
- 52／57 個前版頂層函式 AST 完全相同；另外四個除了標題／版本外一致，每日寫入 payload 未變。
- 無資料庫 migration、無資料庫設定／RLS 變更、無正式資料寫入。不把登入頁正常等同於業務驗收。
- 真實管理員與教練需重新整理／重新登入後確認新入口、查詢及下載。
- 復原只需還原前版程式／版本／文件，不刪除或重匯入交易。

## 證據

- DEPLOY_v1.13.11_20261014_login.jpg：重啟後正常登入頁。
- DEPLOY_v1.13.11_20261014_server.jpg：部署管理畫面。
- VERIFICATION_v1.13.11.md：完整檢核、限制與重現。
- UPGRADE_v1.13.11.md：新路徑與復原說明。

部署證據圖片只保留本機，不公開上傳。此紀錄不包含會員個資、登入密碼、API 金鑰或 Streamlit Secrets。
