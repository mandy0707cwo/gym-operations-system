"""查詢按鈕、會員／ID篩選及私有快照的隔離回歸。"""
import ast
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from confirmed_queries import ConfirmedQuery
from streamlit.testing.v1 import AppTest


class SnapshotTests(unittest.TestCase):
    def test_no_read_before_confirmation(self):
        snapshot = ConfirmedQuery({}, {"id": "a", "role": "admin"}, "test", ("甲",), False)
        self.assertFalse(snapshot.ready)
        with self.assertRaises(ValueError):
            snapshot.load("rows", lambda: self.fail("未確認不應讀取"))

    def test_reuse_copy_and_explicit_refresh(self):
        state = {}; owner = {"id": "a", "role": "admin"}; calls = []
        load = lambda: calls.append(1) or [{"amount": 1050}]
        first = ConfirmedQuery(state, owner, "test", ("甲",), True)
        first.load("rows", load)[0]["amount"] = 0
        again = ConfirmedQuery(state, owner, "test", ("甲",), False)
        self.assertEqual(again.load("rows", load)[0]["amount"], 1050)
        self.assertEqual(len(calls), 1)
        ConfirmedQuery(state, owner, "test", ("甲",), True).load("rows", load)
        self.assertEqual(len(calls), 2)

    def test_criteria_owner_and_role_isolation(self):
        for changed in [{"id": "b", "role": "admin"}, {"id": "a", "role": "coach"}]:
            state = {}; ConfirmedQuery(state, {"id": "a", "role": "admin"}, "test", (), True)
            self.assertFalse(ConfirmedQuery(state, changed, "test", (), False).ready)
        state = {}; ConfirmedQuery(state, {"id": "a"}, "test", ("甲",), True)
        self.assertFalse(ConfirmedQuery(state, {"id": "a"}, "test", ("乙",), False).ready)

    def test_loop_reads_and_memory_bound(self):
        state = {}; owner = {"id": "a"}
        first = ConfirmedQuery(state, owner, "test", (), True)
        for n in range(3): first.load("pages", lambda n=n: [n])
        again = ConfirmedQuery(state, owner, "test", (), False)
        self.assertEqual([again.load("pages", lambda: self.fail("不應重讀")) for _ in range(3)], [[0], [1], [2]])
        for n in range(20): ConfirmedQuery(state, owner, str(n), (), True)
        self.assertLessEqual(len(state), 16)


SCRIPT = '''
import ast
from copy import deepcopy
from datetime import date,datetime
from decimal import Decimal,ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st
from ui_text import section_heading
from confirmed_queries import confirm_query,query_read
st.session_state.setdefault("reads",[])
class Query:
 def __init__(self,name):
  self.name=name
  self.records=deepcopy(st.session_state.get("tables",{}).get(name,[]))
 def select(self,*a): return self
 def order(self,*a,**k): return self
 def eq(self,field,value):
  self.records=[x for x in self.records if x.get(field)==value]; return self
 def in_(self,field,values):
  self.records=[x for x in self.records if x.get(field) in values]; return self
 def gte(self,field,value):
  self.records=[x for x in self.records if str(x.get(field,""))>=value]; return self
 def lte(self,field,value):
  self.records=[x for x in self.records if str(x.get(field,""))<=value]; return self
 def range(self,a,b): self.records=self.records[a:b+1]; return self
 def execute(self):
  st.session_state["reads"].append(self.name)
  return type("Response",(),{"data":self.records})()
class Client:
 def table(self,name): return Query(name)
def client(): return Client()
def admin_client(): return Client()
def coach_options(): return {"虛構教練":"c1"}
def rows(query): return query.execute().data
def paged_rows(builder,*a,**k): return rows(builder())
names={"general_queries_page","financial_report_page","usage_query_tabs","customer_admin_page","installment_payment_admin_page","record_admin_page","_load_record_admin_data","_tax_display_amount","_allocate_payment_net_amounts","usage_net_amount","_excel_bytes","_build_purchase_code_map","course_status_label","usage_sequence_by_date","is_magnetic_wave_course","is_magnetic_wave_operation","is_magnetic_wave_purchase","usage_counts_for_execution","completed_purchase_ids","_bonus_rule_for_date","_bonus_eligibility","_financial_backup_frames"}
tree=ast.parse(Path(APP_PATH).read_text(encoding="utf-8"))
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),"<query-page>","exec"),globals())
me={"id":"c1","role":st.session_state.get("role","admin"),"display_name":"虛構教練"}
{"general":general_queries_page,"financial":financial_report_page,"coach":usage_query_tabs,"customer":customer_admin_page,"installment":installment_payment_admin_page,"record":record_admin_page}[st.session_state.get("view","general")](me)
'''


class QueryUITests(unittest.TestCase):
    def app(self, view="general", **state):
        app = AppTest.from_string("APP_PATH=" + repr(str(ROOT / "app.py")) + "\n" + SCRIPT, default_timeout=30)
        app.session_state["view"] = view
        for key, value in state.items(): app.session_state[key] = value
        app.run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_purchase_third_tab_no_read_until_click_and_intersection(self):
        tables={"profiles":[{"id":"c1","display_name":"虛構教練","role":"coach","active":True}],
                "members":[{"id":"m1","member_name":"測試會員甲"},{"id":"m2","member_name":"測試會員乙"}],
                "purchases":[{"id":"p1","member_id":"m1","coach_id":"c1","purchase_code":"20260414-001","purchase_date":"2026-04-14","created_at":"a","course_name":"測試課程","total_amount":1050,"total_sessions":1},
                             {"id":"p2","member_id":"m2","coach_id":"c1","purchase_code":"20260414-002","purchase_date":"2026-04-14","created_at":"b","course_name":"測試課程","total_amount":2100,"total_sessions":2}],
                "purchase_payments":[{"id":"pay","purchase_id":"p1","paid_date":"2026-04-14","amount":1050}],"session_usages":[],"course_terminations":[]}
        app=self.app(general_query_main_tab="成交總表",general_purchase_mode="會員查詢",tables=tables)
        self.assertEqual(set(app.session_state["reads"]), {"profiles"})
        self.assertEqual(len(app.dataframe),0)
        app.text_input(key="gp_member_search").set_value("會員甲")
        app.text_input(key="gp_purchase_search").set_value("20260414")
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.dataframe[0].value["購買_ID"].tolist(),["20260414-001"])
        count=len(app.session_state["reads"])
        app.run()
        self.assertEqual(len(app.exception),0)
        # 只有教練下拉主檔更新；交易資料保持已確認快照。
        self.assertEqual(app.session_state["reads"][count:],["profiles"])
        self.assertEqual(app.dataframe[0].value["成交金額（未稅）"].sum(),1000)
        app.text_input(key="gp_purchase_search").set_value("20260414-002")
        app.button[0].click().run()
        self.assertEqual(len(app.dataframe),0)
        self.assertEqual(app.metric[0].value,"$ 0")

    def test_financial_and_coach_initial_no_transactions(self):
        for view,state in [("financial",{"financial_report_view":"會員報表"}),
                           ("financial",{"financial_report_view":"每月報表"}),
                           ("financial",{"financial_report_view":"其他報表"}),
                           ("coach",{}),
                           ("coach",{"coach_query_view_usage":"執行時數"}),
                           ("coach",{"coach_query_view_usage":"銷課明細查詢"})]:
            with self.subTest(view=view,state=state):
                app=self.app(view,**state)
                self.assertLessEqual(set(app.session_state["reads"]),{"profiles","members"})
                self.assertEqual(len(app.dataframe),0)

    def test_management_and_installment_initial_no_results(self):
        for view,state in [("customer",{"customer_management_tabs":"查詢／修改"}), ("installment",{}), ("record",{})]:
            with self.subTest(view=view):
                app=self.app(view,**state)
                self.assertLessEqual(set(app.session_state["reads"]),{"profiles"})
                self.assertEqual(len(app.dataframe),0)

    def test_monthly_query_then_display_rerun_does_not_read_transactions(self):
        app=self.app("financial",financial_report_view="每月報表")
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        count=len(app.session_state["reads"])
        app.run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state["reads"][count:],[])

    def test_admin_permission_and_renaming(self):
        app=self.app(role="coach")
        self.assertEqual(app.session_state["reads"],[])
        app=self.app(general_query_main_tab="預收款項")
        self.assertEqual(len(app.button),1)
        self.assertEqual(len(app.dataframe),0)
        self.assertNotIn("實際預收收入",(ROOT/"app.py").read_text(encoding="utf-8"))

    def test_other_general_tabs_wait_for_query(self):
        for tab,mode_key,mode in [("銷課查詢","general_usage_mode","日期區間"),
                                 ("預收款項","general_prepaid_mode","會員查詢"),
                                 ("預收餘額查詢","general_balance_mode","預收餘額（未稅）"),
                                 ("預收餘額查詢","general_balance_mode","預收餘額（含稅）")]:
            app=self.app(general_query_main_tab=tab,**{mode_key:mode})
            self.assertEqual(len(app.button),1)
            self.assertEqual(len(app.dataframe),0)
            self.assertEqual(set(app.session_state["reads"]),{"profiles"})

    def test_customer_selection_keeps_confirmed_results(self):
        tables={"members":[{"id":"m1","member_name":"測試客戶甲","customer_status":"member","active":True},
                           {"id":"m2","member_name":"測試客戶乙","customer_status":"member","active":True}]}
        app=self.app("customer",customer_management_tabs="查詢／修改",tables=tables)
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        selection=app.selectbox(key="customer_edit_select")
        selection.set_value(selection.options[-1]).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(app.dataframe),1)
        self.assertEqual(next(x for x in app.text_input if x.label=="客戶姓名").value,"測試客戶乙")

    def test_every_query_submit_is_assigned(self):
        tree=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
                call=node.value
                if isinstance(call.func,ast.Attribute) and call.func.attr=="form_submit_button" and call.args and isinstance(call.args[0],ast.Constant):
                    self.assertNotEqual(call.args[0].value,"查詢",f"查詢回傳值未使用，行{call.lineno}")

    def test_installment_selection_does_not_reuse_other_purchase_audit(self):
        tables={"members":[{"id":"m1","member_name":"測試甲"},{"id":"m2","member_name":"測試乙"}],
                "profiles":[{"id":"a","display_name":"操作者甲"},{"id":"b","display_name":"操作者乙"}],
                "purchases":[{"id":pid,"member_id":mid,"purchase_date":"2026-04-14","purchase_code":code,"created_at":"a","course_name":"測試課程","payment_plan":"installment","installment_count":2,"total_amount":1050} for pid,mid,code in [("p1","m1","20260414-001"),("p2","m2","20260414-002")]],
                "purchase_payments":[{"id":"pay"+pid,"purchase_id":pid,"amount":500,"installment_no":1,"paid_date":"2026-04-14"} for pid in ["p1","p2"]],
                "purchase_payment_change_logs":[{"purchase_id":pid,"action_type":"correction","installment_no":1,"old_amount":400,"new_amount":500,"reason":reason,"changed_by":who,"changed_at":"2026-04-14T01:00:00"} for pid,reason,who in [("p1","甲紀錄","a"),("p2","乙紀錄","b")]]}
        app=self.app("installment",tables=tables)
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        count=len(app.session_state["reads"])
        selector=app.selectbox(key="installment_admin_purchase")
        selector.set_value(selector.options[-1]).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state["reads"][count:],[])
        audit=next(x.value for x in app.dataframe if "操作者" in x.value.columns)
        self.assertEqual(audit["原因"].tolist(),["乙紀錄"])
        self.assertEqual(audit["操作者"].tolist(),["操作者乙"])


if __name__=="__main__": unittest.main()
