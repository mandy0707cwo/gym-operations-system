"""排班顯示及既有帳號／財務／防重送回歸；只使用離線虛構資料。"""
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
TEST_TEMP=ROOT/'.test-temp';TEST_TEMP.mkdir(exist_ok=True)
tempfile.tempdir=str(TEST_TEMP)
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
logging.disable(logging.WARNING)
assert (ROOT/'VERSION').read_text().strip()=='v1.13.31'
for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:
    compile(path.read_text(encoding='utf-8'),str(path),'exec')
names=['test_schedule_display_v31','test_account_update_form','test_schedule_rest_color',
       'test_schedule_headcounts','test_schedule_compact','test_schedule_leave','test_schedule_allowance',
       'test_scheduling','test_scheduling_ui','test_schedule_export','test_navigation_platforms',
       'test_usage_funds','test_usage_idempotency_ui','test_financial_calculations']
suite=unittest.TestSuite()
for name in names:
    module=importlib.import_module(name)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    for label,test in inspect.getmembers(module,inspect.isfunction):
        if label.startswith('test_'):suite.addTest(unittest.FunctionTestCase(test))
start=time.monotonic()
result=unittest.TextTestRunner(verbosity=1).run(suite)
report={'version':'v1.13.31','base_commit':'fd0d7c2ae32c82a67bb84478a78470008017bd65',
        'tests_run':result.testsRun,'passed':result.testsRun-len(result.skipped)-len(result.errors)-len(result.failures),
        'skipped':len(result.skipped),'errors':len(result.errors),'failures':len(result.failures),
        'successful':result.wasSuccessful(),'seconds':round(time.monotonic()-start,3),
        'scope':'offline AppTest, fictitious profiles and pure business rules',
        'production_modified':False,'schema_changed':False,
        'failed_names':[str(t) for t,_ in result.errors+result.failures]}
(ROOT/'verification_schedule_display_v1.13.31.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
