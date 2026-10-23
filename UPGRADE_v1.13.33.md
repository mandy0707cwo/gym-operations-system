# v1.13.33 升級說明（本機候選）

尚未提交或部署正式系統，不可只上傳Python而省略SQL。

1. 備份正式資料庫及原版本，確認可還原；保留原始班表、稽核紀錄及特殊假別資料。
2. 若仍為v31，先依UPGRADE_v1.13.32.md執行v32 migration；勿重跑已完成的v32 migration。
3. 執行supabase/migrations/20261023134850_schedule_manager_notes_v1_13_33.sql。可安全重跑，版本不符則停止，不自動覆蓋未知函式。
4. 部署完整v33來源，再用主管及管理員驗證：選教練、點日期，班別及備註一起儲存，不需異動原因；教練已確認月份仍鎖定。
5. 核對資料筆數、核准狀態、額度及原財務合計未變；檢查特殊假別有無歷史資料，如有須另確認轉換，不刪資料。

本機展示：python -m streamlit run schedule_demo.py --server.address 127.0.0.1 --server.port 8515 --server.headless true。

驗證：python verify_schedule_manager_v33.py；--database僅允許固定localhost:55439的虛構PostgreSQL，不能指向正式系統。

復原時部署原來源，並由已核對備份或v32原函式定義復原兩支函式；不要重跑含新增欄位／回補資料的整支v32 migration。新寫入班表不應整批覆蓋。
