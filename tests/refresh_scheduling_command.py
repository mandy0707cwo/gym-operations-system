"""僅更新本機候選函式以迭代測試；不連正式Supabase、不寫migration歷史。"""
from pathlib import Path
from test_idempotency_database import sql
ROOT=Path(__file__).resolve().parents[1]
text=(ROOT/'supabase/migrations/20261021083833_staff_scheduling_v1_13_22.sql').read_text(encoding='utf-8')
start=text.index('create function schedule_private.command(')
end=text.index('revoke all on function schedule_private.command(',start)
sql(text[start:end].replace('create function','create or replace function',1))
start=text.index('create function public.staff_schedule_snapshot(')
sql(text[start:].replace('create function','create or replace function',1))
print('Refreshed localhost candidate function only.')
