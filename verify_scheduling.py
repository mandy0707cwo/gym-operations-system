"""針對排班與既有財務界線的隔離測試；不連正式系統。"""
import ast
import importlib
import inspect
import json
import logging
import os
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parent
temp=ROOT/'.test-temp';temp.mkdir(exist_ok=True)
tempfile.tempdir=str(temp);os.environ['TEMP']=os.environ['TMP']=str(temp)
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
logging.disable(logging.WARNING)
for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:compile(path.read_text(encoding='utf-8'),str(path),'exec')
base=json.loads((ROOT/'tests/fixtures/release_v21_contract.json').read_text(encoding='utf-8'))
funcs={n.name:n for n in ast.parse((ROOT/'app.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
assert set(funcs)-set(base['functions'])=={'scheduling_page'}
for name,digest in base['functions'].items():
    if name=='_full_system_backup_bytes':continue
    assert sha256(ast.dump(funcs[name],include_attributes=False).encode()).hexdigest()==digest,name
assert (ROOT/'VERSION').read_text().strip()=='v1.13.29'
names=['test_schedule_rest_color','test_schedule_headcounts','test_schedule_compact','test_schedule_leave','test_schedule_allowance','test_scheduling','test_scheduling_ui','test_schedule_export','test_navigation_platforms','test_usage_funds','test_usage_idempotency_ui','test_financial_calculations']
if '--database' in sys.argv:names=['test_schedule_apply_database','test_schedule_leave_database','test_schedule_allowance_database','test_scheduling_database','test_usage_funds_database','test_idempotency_database']
suite=unittest.TestSuite()
for name in names:
    module=importlib.import_module(name)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    for label,test in inspect.getmembers(module,inspect.isfunction):
        if label.startswith('test_'):suite.addTest(unittest.FunctionTestCase(test))
started=time.monotonic()
result=unittest.TextTestRunner(verbosity=2).run(suite)
summary={'version':'v1.13.29','tests_run':result.testsRun,'successful':result.wasSuccessful(),'errors':len(result.errors),
    'failures':len(result.failures),'skipped':len(result.skipped),'seconds':round(time.monotonic()-started,3),
    'scope':'isolated localhost PostgreSQL' if '--database' in sys.argv else 'offline pure rules and AppTest',
    'production_modified':False,'unchanged_existing_app_functions':len(base['functions'])-1,
    'failed_names':[str(t) for t,_ in result.errors+result.failures]}
(ROOT/('verification_schedule_database.json' if '--database' in sys.argv else 'verification_schedule_ui.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
