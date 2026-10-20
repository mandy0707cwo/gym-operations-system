"""只初始化全新本機虛構庫；沿用已發布交易函式，再套用新 trigger。"""
from pathlib import Path
from test_idempotency_database import sql
import runpy

ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'tests/setup_test_database.py'),run_name='__main__')
sql('create schema finance_private;')
sql('grant select,insert on public.session_usages to authenticated;')
sql((ROOT/'supabase/migrations/20261020023026_usage_funds_guard_v1_13_21.sql').read_text(encoding='utf-8'))
print('Loaded usage funds guard; no production connections.')
