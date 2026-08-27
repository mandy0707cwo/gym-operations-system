# 秀傳運醫營運系統－16GB Windows 本機落地

## 適用規格

- Windows 10/11 Pro 64位元（正式營運建議使用仍受安全更新支援的 Windows 11 Pro）。
- 記憶體16GB以上、SSD可用空間100GB以上。
- 院內有線網路、主機可長時間開機、已停用自動休眠並接UPS。
- 備份可每日留存在主機，並每週手動複製到USB。

## 架構與版本

- Streamlit App：本專案固定套件版本。
- Supabase self-hosted：固定 `self-hosted/v0.8.0`，PostgreSQL 17。
- 啟用服務：PostgreSQL、Auth、PostgREST、Studio、API Gateway及Streamlit。
- 不啟用：Realtime、Storage、imgproxy、Edge Functions、Analytics及Vector。
- App供院內裝置使用8501埠；Supabase API只綁定主機的127.0.0.1，不直接開放給院內其他電腦。

## 安裝順序

1. 在目標電腦升級至16GB記憶體，完成Windows更新並重新開機。
2. 安裝Docker Desktop及Git for Windows，Docker Desktop使用WSL 2模式。
3. 以系統管理員身分開啟PowerShell。
4. 執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\local-deployment\01-Check-Computer.ps1
.\local-deployment\02-Install-Local-System.ps1
```

5. 安裝完成會顯示院內網址，例如 `http://192.168.1.50:8501`。

## 資料搬移

正式資料不可直接以一般 `pg_dump` 搬移。應依Supabase官方方式使用Supabase CLI分別匯出：

```powershell
supabase db dump --db-url "線上資料庫連線字串" -f roles.sql --role-only
supabase db dump --db-url "線上資料庫連線字串" -f schema.sql
supabase db dump --db-url "線上資料庫連線字串" -f data.sql --use-copy --data-only
```

資料搬移必須先在測試環境還原，核對資料筆數、金額合計、登入、權限及RPC，再安排正式切換。`auth.users`會一併搬移，使用者原密碼可保留，但搬移後所有人必須重新登入。

## 每日操作

- 啟動：`03-Start-Local-System.ps1`
- 停止：`04-Stop-Local-System.ps1`
- 每日備份：`05-Backup-Database.ps1`
- 複製最新備份到USB：`06-Copy-Latest-Backup-To-USB.ps1`
- 系統檢查：`07-Health-Check.ps1`
- 設定每日自動備份：以系統管理員執行 `08-Register-Daily-Backup.ps1`

每日備份預設保留30天，並建立SHA-256檢核碼。建議準備兩支BitLocker加密USB輪替，每週至少備份一次；USB不要長時間插在伺服器上。

## 上線前驗收

1. 比對線上與本機主要資料表筆數。
2. 比對課程成交金額、實際預收金額、銷課金額及專案餘額。
3. 使用admin、主管、共用教練與一般教練帳號逐一登入。
4. 驗證一般教練看不到其他教練會員資料。
5. 建立一筆測試課程、付款、銷課、取消及專案紀錄後再刪除測試資料。
6. 執行一次備份，並在獨立測試環境完成還原驗證。
7. 至少連續運作48小時，再決定是否切換。

## 重要限制

- 現階段院內網址使用HTTP，只能作為安裝及驗收測試。正式投入會員與財務資料前，仍需建立院內HTTPS憑證或確認院內網路安全隔離。
- 未設定固定IP前，電腦重新連線後網址可能改變。應在目標電腦確認網段及DHCP範圍後，再設定固定IP或路由器DHCP保留。
- 線上系統在本機驗收完成前保持運作，不進行雙向同步；正式切換時須安排短暫停止輸入，做最後一次資料匯出及還原。
