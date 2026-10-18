"""只初始化已啟動的 127.0.0.1:55439 虛構測試庫；不接受正式主機參數。"""
from pathlib import Path
from test_idempotency_database import sql
ROOT = Path(__file__).resolve().parents[1]
files = [ROOT/'tests/fixtures/idempotency_setup.sql', ROOT/'tests/fixtures/base_database.sql',
    ROOT/'tests/fixtures/idempotency_catalog.sql', ROOT/'migration_purchase_code_v1_13_8.sql',
    ROOT/'tests/fixtures/current_transaction_functions.sql',
    ROOT/'supabase/migrations/20261018111949_purchase_usage_idempotency_v1_13_19.sql']
for path in files:
    sql(path.read_text(encoding='utf-8'))
    print('Loaded:', path.name)
