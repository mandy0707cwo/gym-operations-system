"""本機畫面與財務回歸；不接受正式資料庫連線。"""
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
temporary=ROOT/'.test-temp-v38';temporary.mkdir(exist_ok=True);tempfile.tempdir=str(temporary)
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
runtime=ROOT.parents[1]/'tools/termination_v37_runtime'
if runtime.exists():sys.path.insert(0,str(runtime))
logging.disable(logging.WARNING)
from verify_termination_reversal_v37 import run

if __name__=='__main__':
    for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:compile(path.read_text(encoding='utf-8'),str(path),'exec')
    results=run(['test_finance_report_columns_v38','test_monthly_report_layout','test_online_finance','test_confirmed_queries',
                 'test_termination_reversal_reports','test_financial_backup','test_financial_calculations'])
    report={'version':'v1.13.38','verified_at_taipei':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
            'production_modified':False,'results':results}
    (ROOT/'verification_finance_reports_v1.13.38.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if results['successful'] else 1)
