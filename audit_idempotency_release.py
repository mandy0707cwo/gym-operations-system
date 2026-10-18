"""只允許購課／銷課入口與備份版本字串變更；不連正式服務。"""
import ast
import json
from hashlib import sha256
from pathlib import Path

ROOT=Path(__file__).resolve().parent
after=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
contract=json.loads((ROOT/'tests/fixtures/release_v18_contract.json').read_text(encoding='utf-8'))
old=contract['functions']
new={n.name:ast.dump(n,include_attributes=False) for n in after.body if isinstance(n,ast.FunctionDef)}
allowed={'course_purchase_entry','usage_page','_full_system_backup_bytes'}
assert old.keys()==new.keys()
for name in old:
    if name not in allowed: assert old[name]==sha256(new[name].encode()).hexdigest(),name
assert sha256(new['_full_system_backup_bytes'].replace('v1.13.19','v1.13.18').encode()).hexdigest()==old['_full_system_backup_bytes']
unchanged=['financial_calculations.py','financial_reconciliation.py','finance_reporting.py','project_queries.py',
    'monthly_operation_queries.py','course_query_views.py','confirmed_queries.py','navigation_platforms.py','requirements.txt']
for name in unchanged:assert sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest()==contract['modules'][name],name
for name in ['course_purchase_entry','usage_page']:
    node=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name==name)
    assert len([n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='submit'])==1
    assert 'operation=Operation' in ast.unparse(node).replace(' ','')
    assert 'create_purchase_with_first_payment' not in ast.unparse(node)
    assert '"consume_session"' not in ast.unparse(node)
for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:compile(path.read_text(encoding='utf-8'),str(path),'exec')
assert (ROOT/'VERSION').read_text().strip()=='v1.13.19'
sql=(ROOT/'supabase/migrations/20261018111949_purchase_usage_idempotency_v1_13_19.sql').read_text(encoding='utf-8')
for forbidden in ('drop table','drop policy','disable row level security','create or replace function public.consume_session('):
    assert forbidden not in sql.lower(),forbidden
print(json.dumps({'version':'v1.13.19','unchanged_app_functions':len(old)-len(allowed),
    'unchanged_finance_and_query_modules':unchanged,'only_two_new_operation_entrypoints':True},ensure_ascii=False))
