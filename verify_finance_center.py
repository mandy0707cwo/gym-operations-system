"""隔離回歸入口：固定本工作區暫存目錄，禁止呼叫正式client。"""
from pathlib import Path
import logging
import json
import os
import sys
import tempfile
import unittest
import inspect
import importlib
import time

ROOT=Path(__file__).resolve().parent
temp=ROOT/'.test-temp'
temp.mkdir(exist_ok=True)
tempfile.tempdir=str(temp)
os.environ['TEMP']=os.environ['TMP']=str(temp)
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
logging.getLogger('streamlit.runtime.scriptrunner_utils.script_run_context').setLevel(logging.ERROR)
logging.disable(logging.WARNING)

if __name__=='__main__':
    names=['test_financial_calculations','test_financial_reconciliation','test_historical_alignment','test_finance_center_integration','test_query_views_v1_13_14','test_confirmed_queries','test_online_finance','test_project_queries','test_project_queries_ui','test_course_defaults','test_navigation_platforms','test_ui_text','test_purchase_codes']
    suite=unittest.TestSuite()
    for name in names:
        module=importlib.import_module(name)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for test_name,test in inspect.getmembers(module,inspect.isfunction):
            if test_name.startswith('test_'):suite.addTest(unittest.FunctionTestCase(test))
    started=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (ROOT/'verification_result.json').write_text(json.dumps({
        'version':'v1.13.18','tests_run':result.testsRun,'successful':result.wasSuccessful(),
        'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),
        'failed_names':[str(case) for case,_ in result.errors+result.failures],
        'seconds':round(time.monotonic()-started,3),
        'scope':'isolated fictitious AppTest; no production DB calls'
    },ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
