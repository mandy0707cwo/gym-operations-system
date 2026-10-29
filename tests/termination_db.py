"""限定127.0.0.1:55439/termination_v37；不接受外部資料庫設定。"""
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
PSQL=ROOT.parents[1]/'tools/postgres_idempotency_test/pgsql/bin/psql.exe'
ADMIN='00000000-0000-4000-8000-000000000001'
COACH='00000000-0000-4000-8000-000000000002'
OTHER='00000000-0000-4000-8000-000000000003'
MEMBER='00000000-0000-4000-8000-000000000004'


def sql(query):
    env=dict(os.environ,PGCLIENTENCODING='UTF8')
    for key in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGPASSFILE','PGOPTIONS'):
        env.pop(key,None)
    result=subprocess.run([str(PSQL),'-X','-q','-t','-A','-v','ON_ERROR_STOP=1',
        '-h','127.0.0.1','-p','55439','-U','postgres','-d','termination_v37'],
        input=query,text=True,encoding='utf-8',capture_output=True,env=env,timeout=30)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return [x for x in result.stdout.splitlines() if x.strip()]


def actor(query,who=ADMIN):
    return sql("begin;select set_config('request.jwt.claim.sub','"+who+"',true);"
        "select set_config('request.jwt.claim.role','authenticated',true);set local role authenticated;"
        +query+';commit;')[-1]


def literal(value):return "'"+str(value).replace("'","''")+"'"


def course(kind='expired',bonus=False):
    pid=str(uuid4())
    # 完全虛構；用測試庫原有假會員與教練，金額只供測試，不是商業條件。
    sql(f"insert into public.purchases(id,member_id,coach_id,course_name,purchase_date,expiry_date,total_amount,total_sessions,status,payment_plan,installment_count,purchase_kind,session_hours,created_by) values('{pid}','{MEMBER}','{COACH}','虛構撤銷課程','2026-01-01','2099-12-31',2100,3,'active','full',1,'first',1,'{ADMIN}');insert into public.purchase_payments(purchase_id,installment_no,amount,paid_date,created_by) values('{pid}',1,2100,'2026-01-01','{ADMIN}');")
    result=actor(f"select to_jsonb(public.terminate_course('{pid}','2026-01-31','{kind}',true,{str(bonus).lower()},"+(f"'{COACH}'" if bonus else 'null')+",'虛構中止',null))")
    return pid,json.loads(result)['id']


def reverse(tid,key=None,reason='虛構撤銷',ack=True):
    return f"select public.reverse_course_termination('{key or uuid4()}','{tid}',{literal(reason)},{'true' if ack else 'false'})"
