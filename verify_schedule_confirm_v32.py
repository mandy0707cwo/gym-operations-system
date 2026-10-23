"""離線畫面／規則回歸；--database僅測固定localhost虛構庫，不接受正式連線。"""
import argparse
from datetime import datetime,timedelta,timezone
import importlib
import inspect
import json
import logging
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parent
TMP=ROOT/'.test-temp';TMP.mkdir(exist_ok=True);tempfile.tempdir=str(TMP)
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
logging.disable(logging.WARNING)
OFFLINE=['test_schedule_confirm_special','test_schedule_confirm_special_ui','test_schedule_display_v31',
 'test_account_update_form','test_schedule_rest_color','test_schedule_headcounts','test_schedule_compact',
 'test_schedule_leave','test_schedule_allowance','test_scheduling','test_scheduling_ui','test_schedule_export',
 'test_navigation_platforms','test_usage_funds','test_usage_idempotency_ui','test_financial_calculations']
DATABASE=['test_schedule_confirm_special_database','test_scheduling_database','test_schedule_allowance_database','test_schedule_leave_database']


def run(names):
    suite=unittest.TestSuite()
    for name in names:
        module=importlib.import_module(name);suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for label,test in inspect.getmembers(module,inspect.isfunction):
            if label.startswith('test_'):suite.addTest(unittest.FunctionTestCase(test))
    started=time.monotonic();r=unittest.TextTestRunner(verbosity=1).run(suite)
    return {'tests':r.testsRun,'passed':r.testsRun-len(r.skipped)-len(r.errors)-len(r.failures),
        'skipped':[str(t)+': '+reason for t,reason in r.skipped],'errors':len(r.errors),'failures':len(r.failures),
        'successful':r.wasSuccessful(),'seconds':round(time.monotonic()-started,3),
        'failed_names':[str(t) for t,_ in r.errors+r.failures]}


def db_audit():
    from test_idempotency_database import sql
    data=json.loads(sql("""select jsonb_build_object(
     'tables',(select jsonb_agg(jsonb_build_object('name',c.relname,'rls',c.relrowsecurity,
      'insert',has_table_privilege('authenticated',c.oid,'INSERT'),'update',has_table_privilege('authenticated',c.oid,'UPDATE'),
      'delete',has_table_privilege('authenticated',c.oid,'DELETE'),'backup_read',has_table_privilege('service_role',c.oid,'SELECT')))
      from pg_class c where c.oid in ('public.staff_schedule_special_months'::regclass,'public.staff_schedule_special_days'::regclass)),
     'functions',(select jsonb_agg(jsonb_build_object('name',p.proname,'definer',p.prosecdef,
      'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),'auth_execute',has_function_privilege('authenticated',p.oid,'EXECUTE')))
      from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in
      ('staff_schedule_special_snapshot','staff_schedule_special_save','staff_schedule_manager_confirm')),
     'private_log_read',has_table_privilege('authenticated','schedule_private.special_logs','SELECT'),
     'business_counts',jsonb_build_object('purchases',(select count(*) from public.purchases),
      'payments',(select count(*) from public.purchase_payments),'usages',(select count(*) from public.session_usages)))""")[0])
    assert len(data['tables'])==2 and all(x['rls'] and x['backup_read'] and not any(x[k] for k in ('insert','update','delete')) for x in data['tables'])
    assert len(data['functions'])==3 and all(not x['definer'] and not x['anon_execute'] and x['auth_execute'] for x in data['functions'])
    assert not data['private_log_read']
    guard='\n'.join(sql("select pg_get_functiondef('schedule_private.command(uuid,uuid,date,integer,text,jsonb)'::regprocedure)"))
    assert 'm.coach_locked or m.state' in guard
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',action='store_true');args=parser.parse_args()
    assert (ROOT/'VERSION').read_text().strip()=='v1.13.32'
    for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:compile(path.read_text(encoding='utf-8'),str(path),'exec')
    report={'version':'v1.13.32','base_commit':'1ac301c2376f53a263ac8f06e8c84a17b2053738',
        'verified_at_taipei':datetime.now(timezone(timedelta(hours=8))).isoformat(),'production_modified':False}
    report['offline']=run(OFFLINE)
    if args.database:
        before=db_audit()['business_counts'];report['database']=run(DATABASE);report['security']=db_audit()
        assert before==report['security']['business_counts'],'排班測試不可變更既有營運／財務筆數'
    report['successful']=report['offline']['successful'] and (not args.database or report['database']['successful'])
    (ROOT/'verification_schedule_confirm_v1.13.32.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['successful'] else 1)
