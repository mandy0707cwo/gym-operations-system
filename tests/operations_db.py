"""固定本機127.0.0.1:55442/operations_v42，絕不讀取正式連線設定。"""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PSQL = ROOT.parents[1] / 'tools/postgres_idempotency_test/pgsql/bin/psql.exe'
ADMIN = '00000000-0000-4000-8000-000000000001'
MANAGER = '00000000-0000-4000-8000-000000000002'
COACH = '00000000-0000-4000-8000-000000000003'
SHARED = '00000000-0000-4000-8000-000000000004'
INACTIVE = '00000000-0000-4000-8000-000000000005'
MISSING = '00000000-0000-4000-8000-000000000099'
MIGRATION = ROOT / 'supabase/migrations/20261101022002_operations_completed_counts_v1_13_42.sql'


def sql(query, database='operations_v42'):
    if database not in ('postgres', 'operations_v42'):
        raise ValueError('只允許固定本機假資料庫')
    environment = dict(os.environ, PGCLIENTENCODING='UTF8')
    for key in list(environment):
        if key.startswith('PG') and key != 'PGCLIENTENCODING':
            environment.pop(key, None)
    result = subprocess.run([str(PSQL), '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1',
                             '-h', '127.0.0.1', '-p', '55442', '-U', 'postgres', '-d', database],
                            input=query, capture_output=True, text=True, encoding='utf-8',
                            env=environment, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line.strip()]


def actor(query, who=ADMIN):
    return sql("begin;select set_config('request.jwt.claim.sub','" + who + "',true);"
               "set local role authenticated;" + query + ';rollback;')[-1]


def fingerprint():
    return sql("select md5(string_agg(value,'|' order by name)) from ("
               "select 'profiles' name,md5(coalesce(jsonb_agg(to_jsonb(t) order by id)::text,'')) value from public.profiles t union all "
               "select 'purchases',md5(coalesce(jsonb_agg(to_jsonb(t) order by id)::text,'')) from public.purchases t union all "
               "select 'usages',md5(coalesce(jsonb_agg(to_jsonb(t) order by id)::text,'')) from public.session_usages t union all "
               "select 'terminations',md5(coalesce(jsonb_agg(to_jsonb(t) order by id)::text,'')) from public.course_terminations t) x")[0]


if __name__ == '__main__':
    if sql("select datname from pg_database where datname='operations_v42'", 'postgres'):
        raise SystemExit('本機假資料庫已存在，保留原內容，不自動覆寫。')
    sql('create database operations_v42', 'postgres')
    sql((ROOT / 'tests/fixtures/operations_v42.sql').read_text(encoding='utf-8'))
    before = fingerprint()
    sql(MIGRATION.read_text(encoding='utf-8'))
    assert before == fingerprint()
    print({'local_database': '127.0.0.1:55442/operations_v42', 'fictional_only': True,
           'migration_applied': True, 'rows_unchanged': True})
