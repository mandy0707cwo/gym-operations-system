"""發布工作區檢核：與v1.13.13比較，不執行App、不連正式DB。"""
import ast
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "output" / "release_v1.13.14"
previous = ROOT / "output" / "release_v1.13.13" / "app.py"
before = ast.parse(previous.read_text(encoding="utf-8"))
after = ast.parse((RELEASE / "app.py").read_text(encoding="utf-8"))
functions = lambda tree: {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
old, new = functions(before), functions(after)
assert set(old) == set(new), "正式函式增減未列入範圍"
assert "_paused_daily_pilot_page" not in new, "不可發布暫停活動原型"
protected = {"_tax_display_amount", "usage_net_amount", "_allocate_payment_net_amounts", "_bonus_rule_for_date",
             "_bonus_eligibility", "_build_purchase_code_map", "course_status_label", "usage_sequence_by_date",
             "usage_counts_for_execution", "completed_purchase_ids", "_financial_backup_frames"}
for name in protected:
    assert ast.dump(old[name]) == ast.dump(new[name]), "受保護計算差異：" + name

def database_writes(node):
    return sorted(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
                  and isinstance(call.func, ast.Attribute)
                  and call.func.attr in {"insert", "update", "delete", "rpc"})

# 既有App寫入與RPC的完整參數必須逐函式一致。
for name in old:
    assert database_writes(old[name]) == database_writes(new[name]), "寫入或RPC差異：" + name
for filename in ["course_query_views.py", "monthly_operation_queries.py"]:
    source = (ROOT / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr in {"insert", "delete", "rpc"} for n in ast.walk(tree)), filename
    assert source == (RELEASE / filename).read_text(encoding="utf-8"), "模組快照不同：" + filename
    print(filename, sha256(source.encode("utf-8")).hexdigest())

local = functions(ast.parse((ROOT / "app.py").read_text(encoding="utf-8")))
for name in new:
    assert ast.dump(local[name]) == ast.dump(new[name]), "本機／正式函式不同：" + name
assert (ROOT / "VERSION").read_text().strip() == "v1.13.14"
assert (RELEASE / "VERSION").read_text().strip() == "v1.13.14"
assert 'or "v1.13.14"' in (RELEASE / "app.py").read_text(encoding="utf-8")
print("檢核通過：正式快照無暫停原型；既有資料庫寫入／RPC參數、11個財務與編號函式未改；版本一致。")
