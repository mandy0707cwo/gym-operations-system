"""只對明確127.0.0.1:55439虛構庫套用候選函式，不讀寫正式Supabase。"""
from pathlib import Path
from test_idempotency_database import sql
root=Path(__file__).resolve().parents[1]
assert sql("select exists(select 1 from auth.users where id='00000000-0000-4000-8000-000000000001' and email='test-admin@localhost')")[0]=='t'
snapshot='select (select count(*) from public.purchases)||\':\'||(select count(*) from public.session_usages)||\':\'||(select count(*) from public.staff_schedule_leaves)'
before=sql(snapshot)[0]
sql('begin;'+(root/'supabase/migrations/20261021160257_schedule_apply_v1_13_27.sql').read_text(encoding='utf-8')+'commit;')
assert sql(snapshot)[0]==before
print('Updated candidate command in localhost fictitious schema only; no business rows changed.')
