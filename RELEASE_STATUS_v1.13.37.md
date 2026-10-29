# v1.13.37 發布前檢核紀錄

2026-10-29 已通過134項測試（122離線／畫面／下載＋12本機資料庫），未跳過。使用者已授權備份與上線；驗證不撤銷任何正式課程。

最新範圍備份為 private_backup/snapshot_2026-10-29T01-31-01-888191-00-00：58份來源／結構分檔及manifest，購課283、收款303、銷課3088、中止2、獎金規則1筆，重新讀取筆數與檔案SHA256通過。backup_20261029_0931.zip 共59項、CRC通過，SHA256：19633B84E30AD5D2E7639A0F11E2F8B6289354F09F901F5BD3B4C07408A019AC。私人備份不在來源包或GitHub。

正式migration 20261029014022_course_termination_reversal_v1_13_37 已成功執行。五個來源的原資料筆數、合計及內容雜湊均未變（中止忽略新增空欄）；撤銷0筆，撤銷標記0筆。新表RLS、INVOKER view、單一有效中止索引與直接寫入阻擋已核對；anon不能執行撤銷，公開入口不是SECURITY DEFINER。

安全檢查仍有原已存在的匿名／登入角色可呼叫舊SECURITY DEFINER函式與未啟用外洩密碼保護警告，數量未增加；本次沒有放寬原權限。應另案盤點及驗證，不把這些警告宣稱為安全無虞。參考：https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable 、https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection 。

發布前遠端main核對為04d00e9eea26e5e50c8d4c3e58febcd2b803f4bd。一般Git登入元件受本機環境限制，改用既有GitHub連線建立相同Git樹與提交，仍需以預期SHA、非強制更新main。實際提交SHA、線上載入與登入後唯讀檢查，另記於本機output/課程中止撤銷_20261028_v1.13.37；本檔保存發布前證據，不以資料庫完成等同網站完成。
