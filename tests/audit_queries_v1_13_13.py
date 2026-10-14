"""新版與正式前版的變更範圍檢核，不執行App或正式DB。"""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
before=ast.parse((ROOT/"output/release_v1.13.12/app.py").read_text(encoding="utf-8"))
after=ast.parse((ROOT/"output/release_v1.13.13/app.py").read_text(encoding="utf-8"))
functions=lambda t:{n.name:n for n in t.body if isinstance(n,ast.FunctionDef)}
old,new=functions(before),functions(after)
changed={"usage_query_tabs","record_admin_page","customer_admin_page","installment_payment_admin_page","general_queries_page","financial_report_page","_full_system_backup_bytes"}
for name,node in old.items():
    if name not in changed: assert ast.dump(node)==ast.dump(new[name]),name
for name in changed:
    writes=lambda node:sorted(ast.dump(n) for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {"insert","update","delete","rpc"})
    assert writes(old[name])==writes(new[name]),"寫入或RPC差異："+name
assert "_paused_daily_pilot_page" not in new
source=(ROOT/"app.py").read_text(encoding="utf-8")
local=functions(ast.parse(source))
for name in changed: assert ast.dump(new[name])==ast.dump(local[name]),"本次修改的本機與正式快照差異："+name
assert (ROOT/"VERSION").read_text().strip()=="v1.13.13"
assert (ROOT/"output/release_v1.13.13/VERSION").read_text().strip()=="v1.13.13"
assert 'or "v1.13.13"' in source
print(f"檢核通過：{len(old)-len(changed)}個非本次範圍函式未變、7個指定函式寫入／RPC未變、正式快照與本機一致。")
