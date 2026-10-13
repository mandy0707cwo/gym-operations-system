# v1.13.12 字級驗證紀錄

日期：2026-10-14（Asia/Taipei）。
狀態：本機修改與完整隔離回歸完成；已獲使用者同意，提交部署中，線上啟動結果待確認。

## 結果

- Python 語法檢查：app.py、ui_text.py、正式快照與新增測試通過。
- 完整 181 項隔離回歸單次全部通過（235.322 秒）：前版172項加新增9項原生文字、主標題、權限與業務邏輯檢核。
- 正式 app.py 共45處頁內標題調整，剩餘原生 header 名稱只包含購買及分期、教練查詢、營運總覽、客戶管理；另外每日執行登錄、財務平台與系統管理平台由未改動的 navigation_platforms.py 保留原生大標題。
- 使用 Streamlit 原生 :small 文字並保留粗體；上課預約取消的括號說明保留同一行。沒有新增 CSS、外部字型或改動主題設定。
- 核對目前安裝 Streamlit 1.62.0 前端：tabs 與 label 使用 theme.fontSizes.sm，原生 small 指令同樣使用 theme.fontSizes.sm，因此不以一般 Markdown 本文字級冒充分頁字級。
- 財務平台、系統管理平台、每日執行登錄：AppTest 確認主標題仍為原生 header，內部名稱為原生 small 文字；非管理員管理平台 guard 仍拒絕且無標題／內容讀取。
- 標題包含 Markdown 特殊符號時跳脫；不使用 unsafe HTML，不將名稱誤解析成連結或標籤。
- 前後57個頂層函式，將指定標題呈現及版本差異標準化後，AST全部一致；資料查詢、寫入payload、鍵值、交易、金額、時數、獎金與報表計算未變。
- navigation_platforms.py 原版內容保持一致；角色入口、分頁順序、查詢及下載不變。
- 無 migration、無資料庫或RLS變更、無正式資料寫入。原型在本機保留並持續不公開發布。

## 來源與檔案

- 前版 GitHub main：5bde4cb3266a46f5affdfe6967e82a2c47b990f5，v1.13.11。
- 本次正式 app.py SHA256：506e20d26a5d1cdf58a1ccf432753e7910e7108ebe7cac72d4364450d9258742。
- ui_text.py SHA256：786b997053c7ea7af7c5ddcc6129594ebe818cd50c7172e77ebddbc1d99b7b68。
- 正式快照：output/release_v1.13.12/；文件基於現行 GitHub 文件增補，不直接發布本機未發布原型或私人資料。
- app.py 預設備份版本與兩份 VERSION 為v1.13.12。既有v1.13.10 SQL檔名維持不變。

## 範圍及限制

- 使用Streamlit技能的原生文字規範，不更動全域CSS或主題，以避免影響登入、側欄、表格與金額。
- 內部名稱不再採用大字級heading，因此該層原生heading自動錨點不保留；主功能標題錨點不變。
- 此次範圍是頁內標題；一般內文、金額數字及既有儀表板卡片樣式不改動。
- 測試環境：Streamlit1.62.0、pandas3.0.5、openpyxl3.1.5；正式requirements的pandas2.3.1及其他依賴不變。未宣稱正式環境已驗收。
- AppTest僅虛構角色與資料。未啟動本機預覽網站，也未使用正式帳號登入測試；實際大小仍需提交／部署後登入畫面驗收。
- 已獲使用者同意發布及必要重新啟動；正式啟動結果另行記錄。

## 重現與發布

```powershell
python -X utf8 -m py_compile app.py ui_text.py
python -X utf8 tests/verify_v1_13_12.py
```

使用者已明確同意提交／部署。發布時 app.py 與 ui_text.py 必須同一次提交，升級與復原見 UPGRADE_v1.13.12.md。
