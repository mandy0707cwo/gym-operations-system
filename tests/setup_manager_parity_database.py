"""只處理127.0.0.1:55439明確虛構庫，不連線正式Supabase。"""
from pathlib import Path
from test_idempotency_database import sql

root=Path(__file__).resolve().parents[1]
assert sql("select exists(select 1 from auth.users where id='00000000-0000-4000-8000-000000000001' and email='test-admin@localhost')")[0]=='t'
query="select (select count(*) from public.purchases)||':'||(select count(*) from public.session_usages)||':'||(select count(*) from public.staff_schedule_allowances)"
before=sql(query)
source=(root/'supabase/migrations/20261022021115_schedule_manager_parity_v1_13_29.sql').read_text(encoding='utf-8')
sql('begin;'+source+'commit;')
sql('begin;'+source+'commit;')  # 重複套用不增加權限或更動資料。
assert sql(query)==before
print('Applied manager parity twice in fictitious localhost only; business rows unchanged.')
