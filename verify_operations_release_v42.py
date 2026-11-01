"""營運統計發布驗證；預設離線，--database僅固定本機假資料庫。"""
import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
temporary = ROOT/'.test-temp-v42'
temporary.mkdir(exist_ok=True)
tempfile.tempdir = str(temporary)
sys.path[:0] = [str(ROOT),str(ROOT/'tests')]
runtime = ROOT.parents[1]/'tools/termination_v37_runtime'
if runtime.exists():
    sys.path.insert(0,str(runtime))
logging.disable(logging.WARNING)
from verify_termination_reversal_v37 import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database',action='store_true')
    args = parser.parse_args()
    for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:
        compile(path.read_text(encoding='utf-8'),str(path),'exec')
    results = run(['test_operations_rpc_v42','test_operations_management_v40','test_monthly_account_order_v39',
                   'test_finance_report_columns_v38','test_monthly_report_layout','test_online_finance',
                   'test_confirmed_queries','test_termination_reversal_reports','test_financial_backup','test_financial_calculations'])
    report = {'version':'v1.13.42','verified_at_taipei':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
              'production_modified':False,'offline':results}
    if args.database:
        report['local_database'] = run(['test_operations_rpc_database_v42'])
    report['successful'] = results['successful'] and report.get('local_database',{}).get('successful',True)
    (ROOT/'verification_operations_release_v1.13.42.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(0 if report['successful'] else 1)
