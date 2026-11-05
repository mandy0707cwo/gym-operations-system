"""財務排序離線發布驗證；不接受正式連線設定。"""
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
runtime=ROOT.parents[1]/'tools/termination_v37_runtime'
if runtime.exists(): sys.path.insert(0,str(runtime))
from verify_termination_reversal_v37 import run

if __name__=='__main__':
    for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:
        compile(path.read_text(encoding='utf-8'),str(path),'exec')
    results=run(['test_finance_date_order_v44','test_operations_comparison_v43','test_operations_rpc_v42',
        'test_operations_management_v40','test_monthly_account_order_v39','test_finance_report_columns_v38',
        'test_monthly_report_layout','test_online_finance','test_confirmed_queries',
        'test_termination_reversal_reports','test_financial_backup','test_financial_calculations',
        'test_general_usage_query','test_project_queries','test_project_queries_ui'])
    report={'version':'v1.13.44','verified_at_taipei':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
            'production_modified':False,'offline':results,'successful':results['successful']}
    (ROOT/'verification_finance_date_order_v1.13.44.json').write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    raise SystemExit(0 if report['successful'] else 1)
