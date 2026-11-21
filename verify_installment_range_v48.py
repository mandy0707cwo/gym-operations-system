"""日期區間查詢定向回歸；僅虛構資料，不接受正式資料庫憑證。"""
import ast
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from verify_termination_reversal_v37 import run

ROOT=Path(__file__).resolve().parent
MODULES=['test_installment_range_v48','test_workflow_v47','test_prepaid_purchase_query_v45',
         'test_finance_date_order_v44','test_confirmed_queries','test_financial_backup',
         'test_financial_calculations','test_online_finance']


if __name__=='__main__':
    for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:
        ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
    assert (ROOT/'VERSION').read_text(encoding='utf-8').strip()=='v1.13.48'
    assert 'or "v1.13.48"' in (ROOT/'app.py').read_text(encoding='utf-8')
    result=run(MODULES)
    report={'version':'v1.13.48','checked_at_taipei':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
            'production_modified':False,'modules':MODULES,'syntax_checked':True,'result':result}
    output=ROOT.parents[1]/'output/分期入帳日期區間_20261121_v1.13.48'
    output.mkdir(parents=True,exist_ok=True)
    (output/'驗證結果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(not result['successful'])
