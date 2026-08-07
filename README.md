# 健身房線上營運管理系統

以 Streamlit + Supabase（PostgreSQL / Auth）建立，可供多人遠端登入。包含每日營運、課程購買與最多三期付款、原子化銷課、主管 Dashboard。

## 一、建立資料庫

1. 到 Supabase 建立新 Project。
2. 開啟 **SQL Editor**，貼上並執行 `database.sql` 全文。
3. 到 **Authentication > Users** 建立第一位使用者（Email / Password）。
4. SQL Editor 執行以下指令，把第一位使用者改為主管（替換 Email）：

```sql
update public.profiles p
set role = 'manager'
from auth.users u
where p.id = u.id and u.email = 'manager@example.com';
```

後續使用者可在 Authentication 建立，預設角色為 `coach`。主管角色調整建議只由 Supabase 後台操作。

## 二、本機執行（Windows PowerShell）

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
streamlit run app.py
```

在 `.env` 填入 Supabase **Project Settings > API** 的 Project URL 與 anon/public key。請勿使用 `service_role` key。

## 三、部署到 Streamlit Community Cloud

1. 將本資料夾放入私人 GitHub repository。
2. 登入 Streamlit Community Cloud，建立 App，主程式指定 `app.py`。
3. 在 App 的 **Secrets** 貼上：

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
SUPABASE_SECRET_KEY = "YOUR_SUPABASE_SECRET_KEY"
```

4. Deploy。完成後即可用 HTTPS 網址多人登入。

`SUPABASE_SECRET_KEY` 只用於主管從 App 寄送教練邀請，必須存放於 Streamlit Secrets，絕不可提交到 GitHub。可使用新版 `sb_secret_...`；舊專案則使用 `service_role` key。

## 權限與資料邏輯

- 教練：只能讀取與填寫自己的每日營運、購買與銷課資料。
- 主管：可查看全體教練資料與 Dashboard，也可代為填寫。
- 主管：可在「教練帳號管理」寄出邀請，並啟用或停用教練帳號。
- 所有限制由 PostgreSQL Row Level Security 執行，不只依賴畫面隱藏。
- 每一筆購買可有 1–3 期付款紀錄；同一期不可重複。
- 扣課由資料庫交易函式執行並鎖定購買資料，避免多人同時超扣。
- 一般堂次以 `成交總額 ÷ 原始堂數` 四捨五入至小數 2 位；最後一堂扣除全部剩餘金額。

## 上線前檢核

- 用主管、教練帳號各測試一次登入與權限。
- 建立测试會員與課程，完成全堂數銷課，確認扣款合計等於成交總額。
- 確認成交總額、期款、有效日期與會員姓名正確；系統不會自行認定稅務或收入認列方式。
- 若需更正已扣課紀錄，目前應由主管在 Supabase 後台處理並保留稽核說明；正式營運前建議另建「沖銷」流程，不直接刪除紀錄。
