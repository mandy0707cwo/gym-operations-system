"""只連127.0.0.1的全新虛構庫，禁止用正式資料庫執行。"""
from pathlib import Path
import runpy
from test_idempotency_database import sql
ROOT=Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/'tests/setup_usage_funds_database.py'),run_name='__main__')
sql('grant select on public.profiles to authenticated;')
sql((ROOT/'supabase/migrations/20261021083833_staff_scheduling_v1_13_22.sql').read_text(encoding='utf-8'))
sql((ROOT/'supabase/migrations/20261021091712_schedule_approved_visibility_v1_13_23.sql').read_text(encoding='utf-8'))
sql((ROOT/'supabase/migrations/20261021100055_schedule_allowance_v1_13_25.sql').read_text(encoding='utf-8'))
sql((ROOT/'supabase/migrations/20261021152424_schedule_leave_v1_13_26.sql').read_text(encoding='utf-8'))
sql((ROOT/'supabase/migrations/20261021160257_schedule_apply_v1_13_27.sql').read_text(encoding='utf-8'))
print('Loaded isolated scheduling schema.')
