"""只允許 v19 來源上明確的兩個函式差異；不連正式服務。"""
import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
contract=json.loads((ROOT/'tests/fixtures/release_v19_contract.json').read_text(encoding='utf-8'))
tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
funcs={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
assert funcs.keys()==contract['functions'].keys()
for name,node in funcs.items():
    restored=deepcopy(node)
    if name=='_full_system_backup_bytes':
        source=ast.dump(restored,include_attributes=False).replace('v1.13.20','v1.13.19')
    elif name=='financial_report_page':
        first=next(i for i,n in enumerate(restored.body) if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='report_labels' for t in n.targets))
        assert ast.literal_eval(restored.body[first].value)==['每月報表','體驗項目','單次銷售','教練查詢']
        actual=ast.dump(ast.Module(body=restored.body[first:first+2],type_ignores=[]),include_attributes=False)
        expected=ast.parse('report_labels=["每月報表","體驗項目","單次銷售","教練查詢"]\nif st.session_state.get("financial_report_view") not in report_labels:\n st.session_state["financial_report_view"]=report_labels[0]')
        assert actual==ast.dump(expected,include_attributes=False)
        old=ast.parse('if st.session_state.get("financial_report_view")=="課程中止":\n st.session_state["financial_report_view"]="會員報表"\nreport_labels=["會員報表","其他報表","每月報表","體驗項目","單次銷售","教練查詢"]')
        restored.body[first:first+2]=old.body
        source=ast.dump(restored,include_attributes=False)
    else:
        source=ast.dump(restored,include_attributes=False)
    assert sha256(source.encode()).hexdigest()==contract['functions'][name],name
for path,digest in contract['files'].items():
    if path in ('app.py','verify_finance_center.py'):
        continue
    assert sha256((ROOT/path).read_text(encoding='utf-8').encode()).hexdigest()==digest,path
for path in [*ROOT.glob('*.py'),*(ROOT/'tests').glob('*.py')]:
    compile(path.read_text(encoding='utf-8'),str(path),'exec')
assert (ROOT/'VERSION').read_text().strip()=='v1.13.20'
print(json.dumps({'version':'v1.13.20','unchanged_app_functions':58,
                  'only_runtime_changes':['financial_report_page tab allow-list','backup version fallback'],
                  'database_changes':False},ensure_ascii=False))
