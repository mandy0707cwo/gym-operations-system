"""v37 定向驗證：不接受正式 DB 連線；結果是測試產物，不是上線成功證明。"""
import argparse
from datetime import datetime
import importlib
import inspect
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
TEMP=ROOT/'.test-temp-v37';TEMP.mkdir(exist_ok=True);tempfile.tempdir=str(TEMP)
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
runtime=ROOT.parents[1]/'tools/termination_v37_runtime'
if runtime.exists():sys.path.insert(0,str(runtime))
logging.disable(logging.WARNING)


def run(names):
    suite=unittest.TestSuite()
    for name in names:
        module=importlib.import_module(name)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        for key,test in inspect.getmembers(module,inspect.isfunction):
            if key.startswith('test_') and not inspect.signature(test).parameters:
                suite.addTest(unittest.FunctionTestCase(test))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    return {'tests':result.testsRun,'passed':result.testsRun-len(result.skipped)-len(result.errors)-len(result.failures),
            'errors':len(result.errors),'failures':len(result.failures),'skipped':[str(t)+': '+reason for t,reason in result.skipped],
            'failed_names':[str(t) for t,_ in result.errors+result.failures],'successful':result.wasSuccessful()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',action='store_true');parser.add_argument('--regression',action='store_true');args=parser.parse_args()
    for file in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:compile(file.read_text(encoding='utf-8'),str(file),'exec')
    names=['test_termination_reversal','test_termination_reversal_reports']
    if args.regression:names+=['test_purchase_installment_ui','test_online_finance','test_confirmed_queries','test_financial_backup','test_financial_calculations']
    report={'version':'v1.13.37','verified_at_taipei':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),'production_modified':False,'offline':run(names)}
    if args.database:report['database']=run(['test_termination_reversal_database'])
    report['successful']=report['offline']['successful'] and report.get('database',{}).get('successful',True)
    (ROOT/'verification_termination_reversal_v1.13.37.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['successful'] else 1)
