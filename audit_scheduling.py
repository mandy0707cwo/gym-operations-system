"""本機新排班Schema最小權限核對，不讀客戶或教練明細。"""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from test_idempotency_database import sql
query="""select jsonb_build_object(
 'tables',(select jsonb_agg(jsonb_build_object('name',c.relname,'rls',c.relrowsecurity,
  'insert',has_table_privilege('authenticated',c.oid,'INSERT'),'update',has_table_privilege('authenticated',c.oid,'UPDATE'),
  'delete',has_table_privilege('authenticated',c.oid,'DELETE'),'service_read',has_table_privilege('service_role',c.oid,'SELECT')))
  from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in
   ('staff_schedule_months','staff_schedule_days','staff_schedule_preferences','staff_schedule_logs','staff_schedule_allowances','staff_schedule_allowance_logs','staff_schedule_leaves','staff_schedule_leave_logs')),
 'functions',(select jsonb_agg(jsonb_build_object('name',p.proname,'definer',p.prosecdef,
  'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE')))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in
  ('staff_schedule_command','staff_schedule_operation','staff_schedule_snapshot','staff_schedule_allowance_save','staff_schedule_allowance_snapshot','staff_schedule_leave_save','staff_schedule_leave_snapshot')),
 'receipt_read',has_table_privilege('authenticated','schedule_private.requests','SELECT'),
 'receipt_insert',has_table_privilege('authenticated','schedule_private.requests','INSERT'))"""
result=json.loads(sql(query)[0])
assert len(result['tables'])==8 and len(result['functions'])==7
assert all(t['rls'] and t['service_read'] and not any(t[k] for k in ('insert','update','delete')) for t in result['tables'])
assert all(not f['definer'] and not f['anon_execute'] and f['authenticated_execute'] for f in result['functions'])
assert not result['receipt_read'] and not result['receipt_insert']
guard=sql("select pg_get_functiondef('schedule_private.allowance_save(uuid,date,integer,jsonb)'::regprocedure)")
assert "if r not in ('manager','admin')" in '\n'.join(guard)
policy=sql("select pg_get_expr(polqual,polrelid) from pg_policy where polname='allowance_log_read' and polrelid='public.staff_schedule_allowance_logs'::regclass")
assert len(policy)==1 and 'manager' in policy[0] and 'admin' in policy[0]
result.update(version='v1.13.29',successful=True,scope='localhost fictitious schema only',production_modified=False,
              manager_parity_guard=True,manager_parity_log_policy=True)
(ROOT/'verification_schedule_security.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('Scheduling schema: RLS, restricted table grants, INVOKER facades and private receipts verified.')
