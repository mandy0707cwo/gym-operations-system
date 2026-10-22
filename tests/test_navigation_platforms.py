"""只用虛構角色及模擬資料驗證入口、分頁與原有函式，不接觸正式資料庫。"""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from navigation_platforms import sidebar_pages, DAILY_TABS, FINANCE_TABS, ADMIN_TABS

SCRIPT = '''
import ast
from datetime import date
from pathlib import Path
import streamlit as st
from navigation_platforms import *
names={"daily_page","daily_operation_page","finance_platform_page","system_admin_platform_page"}
nodes=[n for n in ast.parse(Path(APP_PATH).read_text(encoding="utf-8")).body
       if isinstance(n,ast.FunctionDef) and n.name in names]
exec(compile(ast.Module(body=nodes,type_ignores=[]),"<actual-routing>","exec"),globals())
st.session_state["calls"]=[]
st.session_state["reads"]=[]
class Query:
 def __init__(self, name): self.name=name
 def select(self,*a): return self
 def eq(self,*a): return self
 def order(self,*a,**k): return self
 def limit(self,*a): return self
 def execute(self):
  st.session_state["reads"].append(self.name)
  return type("Response",(),{"data":[]})()
class Client:
 def table(self,name): return Query(name)
def client(): return Client()
def rows(q): return q.execute().data
def coach_options(): return {"虛構教練":"test-id"}
def show_table(*a): pass
def record(name):
 def render(me):
  st.session_state["calls"].append(name)
  st.write("已執行:"+name)
 return render
usage_page=record("銷課")
general_queries_page=record("各項查詢")
financial_report_page=record("每月查詢")
data_management_page=record("資料管理")
account_admin_page=record("帳號與權限管理")
me={"role":st.session_state.get("role","admin"),"id":"test-id","display_name":"虛構教練"}
view=st.session_state.get("view","daily")
if view=="daily": daily_page(me)
elif view=="finance": finance_platform_page(me)
else: system_admin_platform_page(me)
'''


class NavigationTests(unittest.TestCase):
    def app(self, view="daily", role="admin", tab=None, formal=False):
        path=ROOT/"output"/"release_v1.13.11"/"app.py" if formal else ROOT/"app.py"
        if not path.exists():
            path=ROOT/"app.py"
        app=AppTest.from_string("APP_PATH="+repr(str(path))+"\n"+SCRIPT,default_timeout=20)
        app.session_state["view"]=view
        app.session_state["role"]=role
        if tab:
            key={"daily":"daily_execution_tab","finance":"finance_platform_tab","system":"system_admin_platform_tab"}[view]
            app.session_state[key]=tab
        app.run()
        self.assertEqual(len(app.exception),0)
        return app

    def test_sidebar_by_role_and_unknown_role(self):
        base=["每日執行登錄","客戶管理","購買及分期","教練查詢"]
        self.assertEqual(sidebar_pages("coach"),base+["排班管理"])
        self.assertEqual(sidebar_pages("shared_coach"),base)
        self.assertEqual(sidebar_pages("manager"),base+["排班管理","營運總覽"])
        self.assertEqual(sidebar_pages("admin"),base+["排班管理","營運總覽","財務平台","系統管理平台"])
        self.assertEqual(sidebar_pages("unknown"),[])
        self.assertEqual(sidebar_pages(None),[])

    def test_exact_tab_order(self):
        self.assertEqual(DAILY_TABS,("銷課登錄","體驗登錄","單堂銷售","專案登錄","活動支援"))
        self.assertEqual(FINANCE_TABS,("各項查詢","每月查詢"))
        self.assertEqual(ADMIN_TABS,("資料管理","帳號與權限管理"))

    def test_default_daily_is_only_usage(self):
        for formal in (False,True):
            app=self.app(formal=formal)
            self.assertEqual([t.label for t in app.tabs],list(DAILY_TABS))
            self.assertEqual(app.session_state["calls"],["銷課"])
            self.assertEqual(app.session_state["reads"],[])

    def test_operation_tabs_do_not_load_other_operations(self):
        expected={"體驗登錄":["operation_item_catalog"],"單堂銷售":["operation_item_catalog"],
                  "專案登錄":["projects","project_catalog"],"活動支援":["event_supports"]}
        for formal in (False,True):
            for label, tables in expected.items():
                with self.subTest(formal=formal,label=label):
                    app=self.app(tab=label,formal=formal)
                    self.assertEqual(app.session_state["calls"],[])
                    self.assertEqual(app.session_state["reads"],tables)

    def test_finance_default_and_switch_only_selected_function(self):
        for label in FINANCE_TABS:
            app=self.app("finance",tab=label)
            self.assertEqual([t.label for t in app.tabs],list(FINANCE_TABS))
            self.assertEqual(app.session_state["calls"],[label])
        app=self.app("finance")
        self.assertEqual(app.session_state["calls"],["各項查詢"])
        app.session_state["finance_platform_tab"]="每月查詢"
        app.run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state["calls"],["每月查詢"])

    def test_system_default_and_switch_only_selected_function(self):
        for label in ADMIN_TABS:
            app=self.app("system",tab=label)
            self.assertEqual([t.label for t in app.tabs],list(ADMIN_TABS))
            self.assertEqual(app.session_state["calls"],[label])

    def test_direct_admin_platform_access_denied_without_calls(self):
        for view in ("finance","system"):
            for role in ("coach","shared_coach","manager","unknown"):
                with self.subTest(view=view,role=role):
                    app=self.app(view,role)
                    self.assertEqual(app.session_state["calls"],[])
                    self.assertEqual(app.session_state["reads"],[])
                    self.assertEqual(len(app.tabs),0)
                    self.assertEqual(len(app.warning),1)

    def test_daily_all_existing_roles_and_invalid_role(self):
        for role in ("coach","shared_coach","manager","admin"):
            app=self.app(role=role)
            self.assertEqual(app.session_state["calls"],["銷課"])
        app=self.app(role="unknown")
        self.assertEqual(app.session_state["calls"],[])
        self.assertEqual(len(app.tabs),0)

    def test_formal_functions_outside_navigation_are_unchanged(self):
        if not (ROOT/"output/release_v1.13.10/app.py").exists():
            self.skipTest("未附歷史快照；此比較需在發布工作區完成。")
        old=ast.parse((ROOT/"output/release_v1.13.10/app.py").read_text(encoding="utf-8"))
        new=ast.parse((ROOT/"output/release_v1.13.11/app.py").read_text(encoding="utf-8"))
        old_funcs={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)}
        new_funcs={n.name:n for n in new.body if isinstance(n,ast.FunctionDef)}
        allowed={"daily_page","usage_page","dashboard_page","financial_report_page","_full_system_backup_bytes"}
        for name, node in old_funcs.items():
            if name not in allowed:
                self.assertEqual(ast.dump(node),ast.dump(new_funcs[name]),name)
        replacements={"銷課表":"銷課登錄","主管 Dashboard":"營運總覽","財務報表":"每月查詢","v1.13.10":"v1.13.11"}
        for name in allowed-{"daily_page"}:
            original=old_funcs[name]
            class Rename(ast.NodeTransformer):
                def visit_Constant(self,node):
                    if isinstance(node.value,str) and node.value in replacements:
                        node.value=replacements[node.value]
                    return node
            Rename().visit(original)
            if name=="usage_page":
                original.body[0].value.func.attr="subheader"
            self.assertEqual(ast.dump(original),ast.dump(new_funcs[name]),name)
        self.assertNotIn("_paused_daily_pilot_page",new_funcs)
        self.assertEqual((ROOT/"navigation_platforms.py").read_bytes(),
                         (ROOT/"output/release_v1.13.11/navigation_platforms.py").read_bytes())

    def test_daily_write_payloads_unchanged(self):
        if not (ROOT/"output/release_v1.13.10/app.py").exists():
            self.skipTest("未附歷史快照；此比較需在發布工作區完成。")
        old=ast.parse((ROOT/"output/release_v1.13.10/app.py").read_text(encoding="utf-8"))
        new=ast.parse((ROOT/"output/release_v1.13.11/app.py").read_text(encoding="utf-8"))
        before=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=="daily_page")
        after=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=="daily_operation_page")
        def writes(node):
            return sorted(ast.dump(n) for n in ast.walk(node) if isinstance(n,ast.Call)
                          and isinstance(n.func,ast.Attribute) and n.func.attr in ("insert","rpc"))
        self.assertEqual(writes(before),writes(after))
        self.assertGreater(len(writes(before)),0)


if __name__=="__main__":
    unittest.main()
