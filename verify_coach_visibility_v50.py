"""停用教練顯示回歸：只用合成資料，不讀正式憑證。"""
import ast
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from verify_termination_reversal_v37 import run

ROOT = Path(__file__).resolve().parent
MODULES = ['test_coach_visibility_v50', 'test_coach_performance_v49',
    'test_operations_management_v40', 'test_operations_comparison_v43',
    'test_installment_range_v48', 'test_workflow_v47', 'test_prepaid_purchase_query_v45',
    'test_finance_date_order_v44', 'test_confirmed_queries', 'test_financial_backup',
    'test_financial_calculations', 'test_online_finance']

if __name__ == '__main__':
    for path in [*ROOT.glob('*.py'), *(ROOT / 'tests').glob('*.py')]:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == 'v1.13.50'
    assert 'or "v1.13.50"' in (ROOT / 'app.py').read_text(encoding='utf-8')
    baseline = json.loads((ROOT.parents[1] / 'output/教練績效_20261121_v1.13.49/source_manifest.json').read_text(encoding='utf-8'))
    for file in ['coach_performance.py', 'coach_performance_repository.py', 'operations_ui.py',
                 'supabase/migrations/20261121061449_coach_performance_monthly_hours_v1_13_49.sql']:
        assert sha256((ROOT / file).read_bytes()).hexdigest() == baseline['source_sha256'][file], file
    result = run(MODULES)
    record = {'version': 'v1.13.50', 'checked_at_taipei': datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
        'production_modified': False, 'database_migration_required': False, 'syntax_checked': True,
        'calculations_and_repository_and_migration_unchanged': True, 'modules': MODULES, 'result': result}
    output = ROOT.parents[1] / 'output/教練績效停用顯示_20261121_v1.13.50'
    output.mkdir(parents=True, exist_ok=True)
    (output / '驗證結果.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))
    raise SystemExit(not result['successful'])
