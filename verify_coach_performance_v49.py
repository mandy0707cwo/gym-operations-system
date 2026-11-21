"""只測虛構資料；不接受正式憑證，不更動正式資料庫。"""
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
from zoneinfo import ZoneInfo

from verify_termination_reversal_v37 import run

ROOT = Path(__file__).resolve().parent
MODULES = ['test_coach_performance_v49', 'test_operations_management_v40', 'test_operations_comparison_v43',
           'test_installment_range_v48', 'test_workflow_v47', 'test_prepaid_purchase_query_v45',
           'test_finance_date_order_v44', 'test_confirmed_queries', 'test_financial_backup',
           'test_financial_calculations', 'test_online_finance']


if __name__ == '__main__':
    for path in [*ROOT.glob('*.py'), *(ROOT / 'tests').glob('*.py')]:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == 'v1.13.49'
    assert 'or "v1.13.49"' in (ROOT / 'app.py').read_text(encoding='utf-8')
    python_result = run(MODULES)
    runtime = os.environ.get('PGLITE_RUNTIME') or str(ROOT.parents[1] / 'outputs/gym-operations-system/output/qa_atomic_runtime/node_modules/.pnpm/@electric-sql+pglite@0.5.8/node_modules/@electric-sql/pglite/dist/index.js')
    if not Path(runtime).is_file() or not shutil.which('node'):
        raise RuntimeError('找不到隔離PostgreSQL測試環境；請設定PGLITE_RUNTIME與Node執行環境，不得以正式資料庫替代。')
    sql = subprocess.run([shutil.which('node'), str(ROOT / 'tests/test_coach_performance_v49.mjs')],
                         cwd=ROOT, env={**os.environ, 'PGLITE_RUNTIME': runtime}, capture_output=True, text=True, encoding='utf-8', timeout=60)
    print(sql.stdout)
    if sql.stderr: print(sql.stderr)
    report = {'version': 'v1.13.49', 'checked_at_taipei': datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
              'production_modified': False, 'syntax_checked': True, 'modules': MODULES,
              'python_result': python_result, 'postgresql_passed': sql.returncode == 0,
              'postgresql_output': sql.stdout, 'postgresql_error': sql.stderr,
              'successful': python_result['successful'] and sql.returncode == 0}
    output = ROOT.parents[1] / 'output/教練績效_20261121_v1.13.49'
    output.mkdir(parents=True, exist_ok=True)
    (output / '驗證結果.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(not report['successful'])
