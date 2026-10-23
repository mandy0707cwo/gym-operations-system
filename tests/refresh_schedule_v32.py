"""開發迭代時只更新固定localhost虛構庫的兩個守門函式，不接受連線參數。"""
from pathlib import Path
from test_idempotency_database import sql
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'supabase/migrations/20261023114054_schedule_confirm_special_v1_13_32.sql').read_text(encoding='utf-8')
definition='\n'.join(sql("select pg_get_functiondef('schedule_private.command(uuid,uuid,date,integer,text,jsonb)'::regprocedure)"))
if 'm.coach_locked or m.state' not in definition:
    start=source.index('do $migration$');end=source.index('end $migration$;',start)+len('end $migration$;')
    sql(source[start:end])
start=source.index('create function schedule_private.public_off_guard()')
end=source.index('end $$;',start)+len('end $$;')
sql(source[start:end].replace('create function','create or replace function',1))
print('Local v32 confirmation/public-off guards match final migration source.')
