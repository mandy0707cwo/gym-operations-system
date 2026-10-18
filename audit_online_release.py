"""唯讀發布範圍驗證；不連線正式服務，不取代財務憑據核實。"""
import ast
from hashlib import sha256
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]/'outputs/gym-operations-system/output/release_v1.13.14/app.py'

def writes(tree):
    return [ast.dump(n,include_attributes=False) for n in ast.walk(tree)
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and n.func.attr in ('insert','update','upsert','delete','rpc')
            and (n.func.attr=='rpc' or any(isinstance(c,ast.Call) and isinstance(c.func,ast.Attribute)
                                         and c.func.attr=='table' for c in ast.walk(n.func.value)))]

def main():
    source=(ROOT/'app.py').read_text(encoding='utf-8')
    tree=ast.parse(source);before=ast.parse(BASE.read_text(encoding='utf-8'))
    assert sha256(BASE.read_bytes()).hexdigest()=='3bcfbf6c0f0309bf870871959a3abf9dad1414c1c754bd8b3713fa6b28c89565'
    assert sorted(writes(tree))==sorted(writes(before)),'前端交易payload或RPC參數不應改變'
    protected=['login','profile','coach_options','_build_purchase_code_map','_bonus_rule_for_date',
               '_bonus_eligibility','completed_purchase_ids','usage_counts_for_execution']
    a={n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    b={n.name:ast.dump(n,include_attributes=False) for n in before.body if isinstance(n,ast.FunctionDef)}
    for name in protected:assert a[name]==b[name],name
    assert 'activity_pilot' not in source
    assert (ROOT/'VERSION').read_text().strip()=='v1.13.18'
    for name in ['README.md','SYSTEM_DOCUMENTATION.md','資料字典.md','CHANGELOG.md','FINANCIAL_CALCULATION_CENTER.md']:
        assert 'v1.13.18' in (ROOT/name).read_text(encoding='utf-8').splitlines()[0],name
    sql=(ROOT/'supabase/migrations/20261018091440_finance_center_v1_13_18.sql').read_text(encoding='utf-8')
    for forbidden in ['disable row level security','drop policy','grant all','truncate ','drop table']:
        assert forbidden not in sql.lower(),forbidden
    assert 'revoke all on all functions in schema finance_private' in sql
    assert 'HISTORICAL_ALIGNMENT' in sql and 'before_rows' in sql and 'batches' in sql
    assert 'set local lock_timeout' in sql[:250]
    assert sql.count('CREATE OR REPLACE FUNCTION public.consume_session(')==1
    assert sql.count('CREATE OR REPLACE FUNCTION public.terminate_course(')==1
    syntax_files=list(ROOT.glob('*.py'))+list((ROOT/'tests').glob('*.py'))
    for path in syntax_files:compile(path.read_text(encoding='utf-8'),str(path),'exec')
    print(json.dumps({'version':'v1.13.18','unchanged_frontend_writes':len(writes(tree)),
                      'protected_functions':len(protected),'syntax_files':len(syntax_files),
                      'no_paused_pilot':True,'no_existing_rls_changes':True},ensure_ascii=False))

if __name__=='__main__':main()
