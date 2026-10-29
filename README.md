# v1.13.38 財務報表欄位

已完成銷課查詢補單欄、每月教練時數／營收帳號欄、跨月補單時數及談單／結單獎金五欄總計，畫面、Excel與完整備份同步。缺少獎金規則另列待確認，不直接歸為不計。四項需求已通過本機驗證並取得發布授權；正式網站載入結果另留發布紀錄。

安裝requirements.txt後執行 `python verify_finance_reports_v38.py` 可用虛構資料驗證，不連正式資料庫。本機候選來源基準為v1.13.37提交22074cebde78bac8f24cabfb7c80aec52c124d76；不要以候選目錄存在視為已部署。

詳細欄位定義見資料字典.md，升級及復原見UPGRADE_v1.13.38.md，驗證範圍見VERIFICATION_v1.13.38.md。本版不新增資料庫migration、不變更稅率或獎金率。

# v1.13.37 課程中止撤銷

系統管理員於「購買及分期 → 課程中止 → 中止記錄」查詢、選擇中止，按「撤銷中止」，填寫原因、勾選款項／獎金確認後按「確認撤銷」。不會自動向銀行收回退款或追回獎金；已付款者須先另行處理。

本版保留原單，沖回記在撤銷當日；歷史截止日前的中止仍有效。課程效期與已銷課不變。部署順序、備份及復原限制見 UPGRADE_v1.13.37.md；測試指令見 VERIFICATION_v1.13.37.md。過期課程恢復後仍受原有有效期限制，不等於允許過期銷課。

# v1.13.36 排班說明精簡與正式發布來源

移除排休進度入口，教練與管理者原有排班／額度／請假操作保留。額度提示改為「本月可休：星期六X天＋國定假日／補假Y天；」。班別人數下方僅保留兩行新圖例；不改人數、額度、星號及稅額計算。

使用者已授權更新正式系統；正式仍為v31，必須先依UPGRADE_v1.13.36.md升級v32／v33／v35排班SQL，再發布v36完整程式。測試資料與私人升級備份不得上傳。實際部署成功及線上抽查另留部署紀錄，不以此來源說明宣稱完成。

# v1.13.35 額度限制與預排草稿（歷史候選）

教練須等主管／管理者核定額度才能排班。點日期或套用班表只在本頁預排，未按儲存草稿不寫入；草稿可排部分日期，不送審、不鎖定。超額不能儲存草稿或確認送出。確認送出一次儲存完整月並送審，成功後整月鎖定。主管及管理員仍可直接更正。

本機測試：python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8517 --server.headless true。先切換測試主管，在排休額度設定核定額度，再切換測試教練。正式升級見UPGRADE_v1.13.35.md，不能只更新Python。

# v1.13.34 請假與上班時段顯示（歷史候選）

請假選單不顯示內部識別碼，仍按唯一ID安全對應原紀錄。班別人數明細將「狀況」改為「請假」，內容為無請假／部分請假／整段請假，未填上班時段仍顯示待確認；「扣除不在班後時段」更名為「實際上班時段」，僅依班表扣除已登錄請假，不代表打卡出勤。原資料、權限與人數計算不變。

新版展示：python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8516 --server.headless true。見UPGRADE_v1.13.34.md。

# v1.13.33 排班更正簡化（歷史候選）

主管／管理員選教練→點日期→班別／時段及備註→儲存修改。不另填異動原因，特殊假別設定分頁移除。已核准狀態及教練整月鎖定保留。升級見UPGRADE_v1.13.33.md；本機僅虛構資料。

在本目錄執行：`python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8515 --server.headless true`。

# v1.13.32 排班確認鎖定與特殊假別（歷史候選描述）

新流程：教練每日選擇先暫存，確認完整月後由主管及管理者修改。特殊假別及排休進度只供主管及管理者管理；確認儲存與核准分開呈現。正式升級步驟見UPGRADE_v1.13.32.md；尚未上線。

# v1.13.31 排班對象標示與草稿提示（正式發布來源）

排班審核的教練選單改為「帳號 姓名」，例如SMC001 黃友宏；只將帳號顯示為大寫，不變更實際登入帳號。儲存草稿後改為短暫確認提示，不再顯示31/31天及尚未送審的長綠框。原有狀態與錯誤提示保留，無需SQL或資料轉換。

# v1.13.30 帳號修改正確帶入（正式發布來源）

系統管理平台→帳號與權限管理→現有帳號：先選帳號，再帶入實際權限及啟用狀態。登入帳號與姓名僅供唯讀核對；此版不新增更名功能。切換帳號放棄尚未送出的修改，重設密碼預設空白。按更新帳號才寫入。

無需執行SQL或資料轉換；本機測試使用虛構帳號及模擬連線，不讀寫正式資料。使用者已授權提交與部署，正式網站實際載入及登入後驗證另留部署紀錄，不以GitHub提交成功代替線上驗收。

# v1.13.29 排班管理正式發布（2026-10-22）

使用者完成測試並授權發布。正式入口仍為 `app.py`，登入後於左側選擇「排班管理」；主管與系統管理員在此模組同權。教練先套用班表、調整日期、儲存草稿及整月送審；審核後才公開至已核准班表。每月額度須由主管或管理員核定，不自行推定國定假日。

本次六支排班migration已於正式資料庫依序執行，8張新增公開表均啟用RLS、禁止直接寫入，7支公開RPC禁止匿名執行。部署前後既有購課、收款、銷課與帳號指紋及原權限相同。未匯入虛構資料、未變更財務計算。程式切換後的線上載入結果另留本機部署紀錄。

部署前已保留原版程式及公開應用資料備份；此應用資料備份不包含Auth、私有操作憑證或金鑰，不等同完整PostgreSQL災難還原備份。復原方式與完整migration順序見 `UPGRADE_v1.13.29.md`。

## 以下保留本機驗收操作說明（歷史階段）

雙擊「開啟排班測試版.cmd」，或 `python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8514`。使用既有requirements.txt環境；啟動檔優先使用這台電腦的已安裝Python。測試服務須保持運行，網址本身不會啟動服務。舊8512／8513頁面不重啟、不轉換其工作階段資料。

已核准班表的「人數簡表」更名為「班別人數」，只留A班／B班／C班／合計。整組人數查詢方式、起訖時間及查詢按鈕已移除，直接顯示所選月份的每日人數。

半日休的原上班區間只完整落在A或B其中一班時歸該班；同時符合兩班或都不符合時列C班，附＊。其他有時段列C班＊；未填時段列待確認，不冒充可用人數。點數字及教練明細仍保留原始班別。合計保留，但不同時段的人相加不表示同一時間都在班。

教練明細的實際例假使用原生藍色底標示，不按星期日推定；不影響原始資料或Excel。主管與系統管理員的排班權限一致，含額度設定及班表下載；不擴及財務、帳號管理或正式系統。底層仍保留異動紀錄，但畫面不新增異動記錄分頁。

本版新增候選SQL：20261022021115_schedule_manager_parity_v1_13_29.sql；只在獨立本機虛構庫驗證。正式部署仍需另行授權、備份與逐版升級。操作／驗證／發布界線見同版本UPGRADE、VERIFICATION與RELEASE_STATUS；打包使用package_scheduling_v29.py。

# 以下為v1.13.28歷史說明

# v1.13.28 核准班表人數簡表（本機測試，未上線）

執行「開啟排班測試版.cmd」，或 `python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8512`。使用既有requirements.txt環境；只使用工作階段的虛構資料，不連正式資料庫。重新整理可能清空示範資料。

已核准班表預設「人數簡表」，可切「教練明細」。日期、星期上下分列；數字為可用／原排，兩人整段不在班顯示0/2，部分時段附＊。點數字看姓名與剩餘在班時段；指定時段須按「查詢人數」才套用，且可用須涵蓋完整查詢時段。這不是實際出勤或沒有預約的人數。

示範：展開「人數簡表虛構範例（僅測試版）」並載入，會建立兩位虛構教練的核准排班與不在班時段；若本次已有排班或請假則拒絕覆蓋。切角色測試同一份工作階段資料。正式入口不匯入這個範例。

已移除扣算說明文字與新排班選單的「週末」，但保留歷史週末紀錄及原排休扣算規則。本版無新SQL，不修改財務、權限或稽核。詳見UPGRADE_v1.13.28.md、VERIFICATION_v1.13.28.md及RELEASE_STATUS_v1.13.28.md；打包改用package_scheduling_v28.py。

# 以下為v1.13.27歷史說明

# v1.13.27 精簡班表介面（本機候選，未上線）

入口：`python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8511`，或「開啟排班測試版.cmd」。同頁切換虛構教練、主管及管理員；不連正式Supabase，刷新可能清空本次展示資料。

選A／B後按「套用班表」：一次儲存預設並補齊本月空白。週日預設例假，既有手動日期不覆蓋；無需另按儲存預設。共同總表上列日期、下列星期，班別附＊表示不在班，完整時間在「查看上班與不在班時段」。所有角色不再顯示異動紀錄分頁或請假異動區，但底層稽核、備份及權限保留。

正式部署尚未執行。新SQL為20261021160257_schedule_apply_v1_13_27.sql，須先有v22、v23、v25及v26結構，再套用v27；不能只更新畫面卻漏掉原子apply動作。操作與升級見UPGRADE_v1.13.27.md；驗證／打包入口為verify_scheduling.py、package_scheduling_v27.py。

# 以下為v1.13.26歷史說明

# v1.13.26 月額度總覽與其他請假（本機候選，未上線）

入口：`python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8510`，或「開啟排班測試版.cmd」。同頁切換測試管理員／主管／教練；只使用本次工作階段的虛構資料，不載入正式連線或秘密，重新整理可能清空。

管理員→排休額度設定：先選月份，查看已核定額度、各教練已排休／剩餘與班表狀態、核定者時間；可試算但不儲存。管理者→請假登錄：先核准教練班表，再新增、修改或作廢單日請假。教練→我的請假只讀本人；已核准班表只對外顯示不在班時段。

新SQL：20261021152424_schedule_leave_v1_13_26.sql。正式升級須明確授權、備份，依v22→v23→v25→v26順序處理；本輪沒有操作正式資料庫或GitHub。詳見UPGRADE_v1.13.26.md。驗證入口verify_scheduling.py，打包入口package_scheduling_v26.py；下方版本均為歷史說明。

# 以下為v1.13.25歷史說明

# v1.13.25 月排休額度（本機候選，未上線）

最新測試入口：`python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8509`，或執行「開啟排班測試版.cmd」。須先具備既有requirements.txt的Python環境。

同頁切換測試管理員→排休額度設定→選月份、填假日／補假明細並核對確認；切回測試教練，即可看到已確認額度、已排與剩餘。沒有事先填入任何正式國定假日。全部只用虛構工作階段，不連正式Supabase，不讀秘密，不永久保存。

說明見UPGRADE_v1.13.25.md。驗證入口為verify_scheduling.py，打包入口為package_scheduling_v25.py；不要用歷史版本打包腳本。正式部署尚未執行，須先經同意並依序套用v22、v23、v25 SQL。

# 以下為v1.13.24歷史說明

# v1.13.24 排班管理（本機候選，未上線）

「儲存草稿」與「整月送審」均在月曆上方。日排班仍會即時儲存；草稿鍵重新確認已儲存日期，不送審、不重複新增。日期格內自訂時段／備註須先按格內儲存。

在已安裝requirements.txt的Python環境執行「開啟排班測試版.cmd」，或：

```powershell
python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8508
```

測試頁上方切換「測試教練甲／乙、測試主管、測試管理員」。請在同一個頁面切身分以保留同一份虛構資料；另開頁面可能是不同工作階段，看不到原頁的測試資料。詳見UPGRADE_v1.13.24.md。驗證入口仍為verify_scheduling.py，打包入口改為package_scheduling_v24.py。正式部署尚未執行；既有SQL與財務規則未改。

# 以下為v1.13.23歷史說明

# v1.13.23 排班管理（獨立測試候選，未上線）

最新操作：教練在「我的排班」只填自己的精簡月曆，點日期後選班別。主管／管理員在「排班審核」處理各教練；「已核准班表」另外提供整月共同總表，未核准不公開。

安全入口仍是schedule_demo.py（虛構資料、工作階段保存、不連正式系統）。在已安裝requirements.txt的Python環境執行：

```powershell
python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8507
```

或執行「開啟排班測試版.cmd」。完整步驟見UPGRADE_v1.13.23.md；驗證入口為`python verify_scheduling.py`。正式部署前須經確認並依序套用v22與v23兩份migration，本次均未對正式庫執行。打包入口為package_scheduling_v23.py；較舊package／audit／verification文件為歷史紀錄，不代表新版已發布。

# 以下為v1.13.22歷史說明，不代表本版操作方式

# v1.13.22 排班管理（獨立測試候選，未上線）

提供全部教練整月行事曆、個人填寫、週日例假預設但可改、一鍵補齊A／B班、整月送審及異動留痕。不設跨月鎖；既有營運、財務、獎金計算不變。

**安全試用入口是schedule_demo.py，不是app.py。** 前者只有兩位虛構教練，沒有正式client、.env或Secrets，資料僅在本次瀏覽器工作階段中保留。可切換虛構教練／主管／管理員試操作，但不代表正式登入或永久儲存。

在安裝既有requirements.txt的環境，於本資料夾執行：

```powershell
python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8506
```

也可執行「開啟排班測試版.cmd」。本次未自動啟動瀏覽器或正式App；若8506被其他程式使用，請改用空閒本機埠。

測試入口：`python verify_scheduling.py`。本機資料庫另依UPGRADE_v1.13.22.md設定。正式資料庫需先經確認再套用本版migration，才能部署app.py及配套模組；不要只上傳app.py。所有發布狀態見RELEASE_STATUS_v1.13.22.md。

# 以下為既有v1.13.21紀錄

# v1.13.21 銷課實收額檢查

一般教練不足實際預收餘額時暫停銷課，畫面與資料庫雙重檢查。其他角色維持既有權限並顯示不足警告；未新增管理員欠款授課核准流程。歷史交易、財務中心、未稅尾差及購課／銷課操作碼不變。

必須先確認備份，再套用本版 migration，最後部署 `app.py` 與新增的 `usage_funds.py`；勿只上傳單一檔案。正式資料庫已套用本版限制，GitHub及雲端狀態見 [發布紀錄](RELEASE_STATUS_v1.13.21.md)。詳見 [升級與復原](UPGRADE_v1.13.21.md) 及 [驗證結果](VERIFICATION_v1.13.21.md)。本版測試使用本機虛構資料，不呼叫正式銷課 API。

# v1.13.20 每月查詢分頁精簡（2026-10-20）

財務平台 → 每月查詢只保留「每月報表、體驗項目、單次銷售、教練查詢」；移除會員報表、其他報表入口。舊分頁狀態自動回每月報表。「各項查詢」、完整備份及歷史資料保留；不改金額計算、權限或購課／銷課防重送。不需新 SQL。更新範圍與驗證見 UPGRADE_v1.13.20.md、VERIFICATION_v1.13.20.md。

# 以下為 v1.13.19 購課／銷課防重送紀錄

此版先套用新 migration，再部署 app.py 與 operation_requests.py；沒有新 SQL 時畫面不退回舊 API。使用與復原見 UPGRADE_v1.13.19.md。財務計算引擎仍為 v1.13.18，規則不變。

# v1.13.18 正式共同計算中心

2026-10-18 已提交並部署，台灣18:03完成啟動，登入頁正常；資料庫更正及逐筆勾稽完成。實際發布紀錄見 [RELEASE_STATUS_v1.13.18.md](RELEASE_STATUS_v1.13.18.md)。

Streamlit + Supabase 線上營運系統。主要入口、教練權限、含稅輸入及獎金機制維持；財務未稅保存、查詢與下載統一新規格。發布結果另見本版驗收與發布紀錄。

安裝：`python -m pip install -r requirements.txt`。測試：`python verify_finance_center.py`。啟動：`python -m streamlit run app.py`。憑證沿用本機／Streamlit Secrets，禁止放進Git或交談。

必須先核對備份並依 [v1.13.18 升級步驟](UPGRADE_v1.13.18.md)套用資料庫遷移，再同次部署程式與相依模組。不要只上傳 app.py。沒有任何自動啟動、付費服務或新增雲端專案。

歷史更正原值及交易稽核保存在 `finance_private`，一般帳號不可存取。此版本不代表已核實原憑據、銀行對帳或完成備份還原測試。

## 以下為保留的 v1.13.17 離線候選紀錄（已由 v1.13.18 取代）

建立共同 Decimal 計算、逐堂固定未稅與最後一堂尾差、歷史副本全期間與截止日試算、逐筆及月份差異清單。體驗／單次兩頁共用明細、合計及下載；其餘報表、正式未稅保存與更正資料表尚未全部接入，不代表整套系統已統一。範圍見[共同計算中心](FINANCIAL_CALCULATION_CENTER.md)、[本版操作邊界](UPGRADE_v1.13.17.md)與[驗證紀錄](VERIFICATION_v1.13.17.md)。

安裝原requirements.txt環境後，在本資料夾執行`python verify_finance_center.py`；啟動App仍是`python -m streamlit run app.py`。App啟動會使用既有設定，尚未核准前不要用正式帳號測試寫入。本次只執行隔離AppTest，沒有啟動連正式資料庫的服務。

副本試算指令（路徑必須替換成實際數值快照；本包不含客戶資料）：

```powershell
python dry_run_history.py 'C:/path/to/private_finance_snapshot.json' --output 'C:/path/to/new_review_folder/simulation.json' --defer-restore-test
```

可加 `--cutoff 2026-08-31`；完整課程分配先於截止日篩選，不以實際服務日期回放。`--defer-restore-test` 僅記錄使用者同意暫緩，不能把還原驗證改成已通過。每次指定新結果目錄，不覆蓋前版。輸出試算摘要、逐筆差異、月份影響及可追溯 JSON，不包含正式寫入程式。

本次資料庫備份已完成匯出檢核，但完整還原測試依使用者同意暫緩；尚未修改正式歷史資料。以下既有版本說明屬歷史功能紀錄，不代表本候選版已部署。

> v1.13.14 已發布：會員課程欄位調整、成功購課後顯示當月資料；每月查詢新增體驗項目與單次銷售的區間／截止日明細、含稅總計及下載，移除重複標題。依使用者確認直接沿用原始含稅金額，不再加稅。不需 SQL；2026-10-15台灣16:49自動更新完成，登入頁正常。見 [UPGRADE_v1.13.14.md](UPGRADE_v1.13.14.md)。

> v1.13.13 完整回歸與補充檢核通過；已提交並部署，重啟及登入頁正常：成交總表新增會員／ID查詢，實際預收收入更名預收款項，按查詢後才帶入結果。app.py與confirmed_queries.py已同次發布，不需SQL。見[UPGRADE_v1.13.13.md](UPGRADE_v1.13.13.md)。

# 秀傳運醫營運系統

# 秀傳運醫營運系統

> v1.13.12 已發布：主功能同名標題保留原大小，其餘45處頁內標題統一為分頁字級。採原生 small 文字，不新增 CSS 或改動主題、資料及計算。線上重啟與登入頁確認正常。說明見 [UPGRADE_v1.13.12.md](UPGRADE_v1.13.12.md)、[VERIFICATION_v1.13.12.md](VERIFICATION_v1.13.12.md)。

> v1.13.11 已發布（172 項檢核通過）：左側整併為每日執行登錄、營運總覽、財務平台、系統管理平台，客戶管理／購買及分期／教練查詢保留。財務平台包含各項查詢、每月查詢（原財務報表全部內容）；系統管理平台包含資料管理、帳號與權限管理。兩平台仍僅管理員使用。無 SQL、無帳務變動。說明見 [UPGRADE_v1.13.11.md](UPGRADE_v1.13.11.md)、[VERIFICATION_v1.13.11.md](VERIFICATION_v1.13.11.md)。

> v1.13.10 已發布：課程名稱管理新增選填課程堂數、成交總金額（含稅）及備註；選課有值才帶入，未設定留白，客戶與課程備註分行保留。正式 SQL course_purchase_defaults_v1_13_10（20261013150637）已完成；程式已提交，2026-10-13 台北 23:13:47.180 完成線上重啟，登入頁正常，業務操作待管理員登入驗收。詳見 output/RELEASE_STATUS_v1.13.10.md。不回溯修改既有購課。操作見 [UPGRADE_v1.13.10.md](UPGRADE_v1.13.10.md)，驗證見 [VERIFICATION_v1.13.10.md](VERIFICATION_v1.13.10.md)。

> v1.13.9 已發布：課程中止拆分逾期／退費，中止記錄增加含稅／未稅分頁及對應 Excel；財務報表移除獨立中止入口，月報及備份保留。不需 SQL；2026-10-12 台北 16:20:48.651 完成線上重啟，登入頁正常，業務操作待管理員登入驗收。操作見 [UPGRADE_v1.13.9.md](UPGRADE_v1.13.9.md)，驗證見 [VERIFICATION_v1.13.9.md](VERIFICATION_v1.13.9.md)。正式發布採獨立快照，保留未發布活動原型。

> v1.13.8：固定購課編號修正。正式 SQL 已於 2026-10-12 完成，購課、付款及銷課原資料校驗保持一致。部署與驗收請見 [VERIFICATION_v1.13.8.md](VERIFICATION_v1.13.8.md)；升級操作見 [UPGRADE_v1.13.8.md](UPGRADE_v1.13.8.md)。僅發布正式快照，不包含暫停活動原型。

> v1.13.6：購買及分期分為課程購買、登錄後續期款及僅管理員可操作的課程中止；成功確認後清空欄位。購課及首期付款改為同一交易，資料庫拒絕任一步均回滾。正式 migration atomic_purchase_v1_13_6 已執行並驗證；使用者已同意提交部署，線上完成狀態以部署紀錄為準。本版包含未單獨發布的 v1.13.5，不啟用活動方案測試。操作見 [UPGRADE_v1.13.6.md](UPGRADE_v1.13.6.md)，測試及既有安全警示見 [VERIFICATION_v1.13.6.md](VERIFICATION_v1.13.6.md)。

> v1.13.4：已儲值專案截止日期欄位更名為「總儲值金額(含稅)」；日期區間在執行日期後新增專案名稱，畫面與 Excel 同步。計算與權限不變，不需 SQL。2026-10-04 使用者已同意發布；線上完成狀態以部署紀錄為準。操作見 [UPGRADE_v1.13.4.md](UPGRADE_v1.13.4.md)，測試見 [VERIFICATION_v1.13.4.md](VERIFICATION_v1.13.4.md)。

> 發布版本：v1.13.3（2026-10-04 已同意提交及部署，線上完成狀態以部署紀錄為準）。專案查詢金額整元顯示、日期由舊到新；日期區間表格移除前期餘額；截止日期餘額總計列於表格及 Excel 最後一列。原始精度與計算不變，不需 SQL。詳見 [UPGRADE_v1.13.3.md](UPGRADE_v1.13.3.md)、[CHANGELOG_v1.13.3.md](CHANGELOG_v1.13.3.md)、[SYSTEM_DOCUMENTATION_v1.13.3.md](SYSTEM_DOCUMENTATION_v1.13.3.md)、[資料字典_v1.13.3.md](資料字典_v1.13.3.md)、[VERIFICATION_v1.13.3.md](VERIFICATION_v1.13.3.md)。活動方案試行暫停，不在發布範圍。


完整功能、權限、資料邏輯、部署、備份及維護說明請參考 [`SYSTEM_DOCUMENTATION.md`](SYSTEM_DOCUMENTATION.md)；歷次變更請參考 [`CHANGELOG.md`](CHANGELOG.md)。

以 Streamlit + Supabase（PostgreSQL / Auth）建立，可供多人以系統帳號與密碼遠端登入。包含每日營運、課程購買與最多三期付款、原子化銷課、主管 Dashboard，以及 admin 帳號與權限管理。

院內Windows本機落地請參考 `LOCAL_DEPLOYMENT.md`。v1.12.0起提供16GB記憶體規格的Docker部署、健康檢查、每日備份與USB備份工具；本機驗收完成前應保留線上系統。

升級至 v1.12.16 時，請先在 Supabase SQL Editor 執行 `migration_usage_makeup_v1_12_16.sql`，再部署新版 App。此更新新增補單與實際銷課日期；兩個日期跨不同年月時，不列入教練執行時數。

系統管理員可在「資料管理 → 資料匯入／匯出 → 一鍵下載備份」下載完整Excel資料備份。檔案保留資料庫UUID與關聯欄位，但基於安全限制不包含登入密碼、API金鑰及Streamlit Secrets；此功能不能取代Supabase資料庫層級備份。

## 一、建立資料庫

1. 到 Supabase 建立新 Project。
2. 開啟 **SQL Editor**，貼上並執行 `database.sql` 全文。
3. 到 **Authentication > Users** 建立第一位使用者（Email / Password）。
4. SQL Editor 執行以下指令，把第一位使用者改為主管（替換 Email）：

```sql
update public.profiles p
set role = 'admin'
from auth.users u
where p.id = u.id and u.email = 'manager@example.com';
```

第一位使用者設為 `admin` 後，其餘帳號直接從 App 的「帳號與權限管理」建立，不需使用 Email。

既有專案更新時，請在 SQL Editor 執行 `migration_username_admin.sql`。最早建立的主管會升級為 `admin`，登入後可在「帳號與權限管理」轉換為不含 Email 的系統帳號。

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

### v1.1.0 專案功能更新

既有系統請在 Supabase SQL Editor 執行 `migration_project_v1_1_0.sql`，再等待 Streamlit 重新部署。

- 專案用於非會員的特定案件，與會員課程分開。
- 新增專案時可選擇「已儲值」或「未儲值」；已儲值必須輸入實際儲值金額。
- 專案建立後，再管理該專案的操作項目、時數與價格。
- 每日營運專案依操作項目與數量計算金額；已儲值專案餘額不足時不允許建立紀錄。
- 財務報表第四分頁提供已儲值使用明細、儲值狀況及未儲值使用明細。
- 既有專案會先保留為未儲值。請由管理員將需要儲值的專案改為已儲值並輸入實際儲值金額；系統不會自行假設該金額。

`SUPABASE_SECRET_KEY` 只用於主管從 App 寄送教練邀請，必須存放於 Streamlit Secrets，絕不可提交到 GitHub。可使用新版 `sb_secret_...`；舊專案則使用 `service_role` key。

## 權限與資料邏輯

- 教練：只能讀取與填寫自己的每日營運、購買與銷課資料。
- 主管：可查看全體教練資料與 Dashboard，也可代為填寫。
- 系統管理員：admin 可直接建立帳號／初始密碼、指定教練或主管權限、重設密碼及停用帳號。
- 所有限制由 PostgreSQL Row Level Security 執行，不只依賴畫面隱藏。
- 每一筆購買可有 1–3 期付款紀錄；同一期不可重複。
- 扣課由資料庫交易函式執行並鎖定購買資料，避免多人同時超扣。
- 含稅銷課金額一般堂次以 `成交總額 ÷ 原始堂數` 四捨五入至小數 2 位，最後一堂扣除全部剩餘含稅金額。
- 未稅銷課金額以整筆課程未稅總額為準；一般堂次使用固定未稅金額，最後一堂扣除先前已入帳未稅金額後吸收全部尾差。

## 上線前檢核

- 用主管、教練帳號各測試一次登入與權限。
- 建立测试會員與課程，完成全堂數銷課，確認扣款合計等於成交總額。
- 確認成交總額、期款、有效日期與會員姓名正確；系統不會自行認定稅務或收入認列方式。
- 若需更正已扣課紀錄，目前應由主管在 Supabase 後台處理並保留稽核說明；正式營運前建議另建「沖銷」流程，不直接刪除紀錄。
# v1.8.0 獎金規則升級

既有系統升級至 v1.8.0 時，請先在 Supabase SQL Editor 執行 `migration_bonus_rules_v1_8_0.sql`，再等待 Streamlit 重新部署。初始規則為談單 3%、結單 4%，醫生轉介首購不計獎金。
