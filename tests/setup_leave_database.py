"""只在既有127.0.0.1:55439虛構排班庫迭代候選新schema，不連正式Supabase。"""
from pathlib import Path
from test_idempotency_database import sql
root=Path(__file__).resolve().parents[1]
assert sql("select exists(select 1 from auth.users where id='00000000-0000-4000-8000-000000000001' and email='test-admin@localhost')")[0]=='t'
assert sql("select to_regclass('public.staff_schedule_leaves') is null")[0]=='t','新表已存在，停止避免覆寫'
before=sql('select count(*) from public.purchases')[0]
sql((root/'supabase/migrations/20261021152424_schedule_leave_v1_13_26.sql').read_text(encoding='utf-8'))
assert sql('select count(*) from public.purchases')[0]==before
print('Loaded new candidate leave schema in localhost fictitious database only.')
