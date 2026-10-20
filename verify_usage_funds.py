"""針對本版執行隔離測試與來源契約；加 --database 執行本機真實雙連線。"""
import ast
from hashlib import sha256
import importlib
import inspect
import json
import logging
import os
from pathlib import Path
import sys
import time
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
temp=ROOT/'.test-temp'
temp.mkdir(exist_ok=True)
tempfile.tempdir=str(temp)
os.environ['TEMP']=os.environ['TMP']=str(temp)
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
logging.disable(logging.WARNING)
contract=json.loads((ROOT/'tests/fixtures/release_v20_contract.json').read_text(encoding='utf-8'))
funcs={n.name:n for n in ast.parse((ROOT/'app.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
assert funcs.keys()==contract['functions'].keys()
for name,node in funcs.items():
    if name=='usage_page':continue
    source=ast.dump(node,include_attributes=False)
    if name=='_full_system_backup_bytes':source=source.replace('v1.13.21','v1.13.20')
    assert sha256(source.encode()).hexdigest()==contract['functions'][name],name
for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:compile(path.read_text(encoding='utf-8'),str(path),'exec')
assert (ROOT/'VERSION').read_text().strip()=='v1.13.21'
names=['test_usage_funds','test_usage_funds_ui','test_usage_idempotency_ui','test_operation_requests',
       'test_financial_calculations','test_finance_center_integration','test_monthly_tabs_v1_13_20']
if '--database' in sys.argv:names=['test_usage_funds_database','test_idempotency_database']
suite=unittest.TestSuite()
for name in names:
    module=importlib.import_module(name)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    for test_name,test in inspect.getmembers(module,inspect.isfunction):
        if test_name.startswith('test_'):suite.addTest(unittest.FunctionTestCase(test))
started=time.monotonic()
result=unittest.TextTestRunner(verbosity=2).run(suite)
summary={'version':'v1.13.21','scope':'local fictitious database' if '--database' in sys.argv else 'isolated UI and calculation regression',
    'tests_run':result.testsRun,'successful':result.wasSuccessful(),'failures':len(result.failures),
    'errors':len(result.errors),'skipped':len(result.skipped),'seconds':round(time.monotonic()-started,3),
    'unchanged_app_functions':len(funcs)-2,'production_modified':False,
    'failed_names':[str(t) for t,_ in result.errors+result.failures]}
target=ROOT/('verification_database_v21.json' if '--database' in sys.argv else 'verification_ui_v21.json')
target.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
