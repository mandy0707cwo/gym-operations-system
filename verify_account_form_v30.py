"""帳號表單及既有營運／財務規則的離線回歸；絕不連正式資料庫。"""
import ast
import hashlib
import importlib
import inspect
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parent
TEST_TEMP=ROOT/".test-temp"
TEST_TEMP.mkdir(exist_ok=True)
tempfile.tempdir=str(TEST_TEMP)
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
logging.disable(logging.WARNING)
BASE_COMMIT="85dfd34dc736c7114cfb17f2174ac640e47c2747"
if (ROOT/".git").exists():
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()==BASE_COMMIT
else:
    assert json.loads((ROOT/"tests/fixtures/account_form_v29_contract.json").read_text(encoding="utf-8"))["base_commit"]==BASE_COMMIT
assert (ROOT/"VERSION").read_text().strip()=="v1.13.30"
for path in [*ROOT.glob("*.py"),*(ROOT/"tests").glob("*.py")]:
    compile(path.read_text(encoding="utf-8"),str(path),"exec")

names=["test_account_update_form","test_schedule_rest_color","test_schedule_headcounts",
       "test_schedule_compact","test_schedule_leave","test_schedule_allowance","test_scheduling",
       "test_scheduling_ui","test_schedule_export","test_navigation_platforms","test_usage_funds",
       "test_usage_idempotency_ui","test_financial_calculations"]
suite=unittest.TestSuite()
for name in names:
    module=importlib.import_module(name)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    for label,test in inspect.getmembers(module,inspect.isfunction):
        if label.startswith("test_"):suite.addTest(unittest.FunctionTestCase(test))
start=time.monotonic()
result=unittest.TextTestRunner(verbosity=1).run(suite)
summary={"version":"v1.13.30","base_commit":BASE_COMMIT,"tests_run":result.testsRun,
         "passed":result.testsRun-len(result.skipped)-len(result.errors)-len(result.failures),
         "skipped":len(result.skipped),"errors":len(result.errors),"failures":len(result.failures),
         "successful":result.wasSuccessful(),"seconds":round(time.monotonic()-start,3),
         "scope":"offline AppTest with fictitious accounts; pure rules; no production writes",
         "production_modified":False,"changed_financial_records":0,
         "failed_names":[str(t) for t,_ in result.errors+result.failures]}
(ROOT/"verification_account_form_v1.13.30.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
