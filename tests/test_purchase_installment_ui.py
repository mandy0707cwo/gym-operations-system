"""以虛構資料與模擬寫入檢查分頁、權限及成功後清空；不連正式資料庫。"""
from datetime import date, timedelta
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
import ast
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import streamlit as st
names={"rows","purchase_page","course_purchase_entry","installment_payment_entry",
       "_entry_saved","_entry_success","_confirmed_write","course_termination_report_page",
       "_build_purchase_code_map"}
tree=ast.parse(Path(APP_PATH).read_text(encoding="utf-8"))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
exec(compile(ast.Module(body=nodes,type_ignores=[]),"<production-functions>","exec"),globals())
if "db" not in st.session_state:
 st.session_state.db={
  "members":[{"id":"m","member_name":"虛構客戶","phone":"000","active":True,
              "responsible_coach_id":"c","referral":"測試轉介","note":"測試備註"}],
  "course_catalog":[{"course_name":"測試課程","course_type":"訓練","report_category":"測試分類","session_hours":1,"active":True}],
  "purchases":[{"id":"p","member_id":"m","course_name":"測試課程","purchase_date":"2026-07-01","created_at":"2026-07-01",
                "total_amount":10500,"total_sessions":10,"installment_count":3,"payment_plan":"installment"}],
  "purchase_payments":[{"id":"first","purchase_id":"p","installment_no":1,"amount":1050,"paid_date":"2026-07-01"}],
  "purchase_balances":[{"purchase_id":"p","member_name":"虛構客戶","course_name":"測試課程","coach_id":"c",
                        "remaining_sessions":8,"remaining_amount":8400,"status":"active","expiry_date":"2027-07-01"}],
  "course_terminations":[],
 }
 st.session_state.reads=[]
 st.session_state.writes=[]
class Query:
 def __init__(self,table,action="select",payload=None):
  self.table=table;self.action=action;self.payload=payload
  self.records=list(st.session_state.db.get(table,[]))
 def select(self,*_): return self
 def order(self,*_,**__): return self
 def insert(self,payload): self.action="insert";self.payload=payload;return self
 def eq(self,field,value): self.records=[x for x in self.records if x.get(field)==value];return self
 def gt(self,field,value): self.records=[x for x in self.records if x.get(field,0)>value];return self
 def in_(self,field,values): self.records=[x for x in self.records if x.get(field) in values];return self
 def gte(self,field,value): self.records=[x for x in self.records if str(x.get(field))>=value];return self
 def lte(self,field,value): self.records=[x for x in self.records if str(x.get(field))<=value];return self
 def execute(self):
  if self.action=="select":
   st.session_state.reads.append(self.table);return SimpleNamespace(data=self.records)
  if self.table=="create_purchase_with_first_payment":
   if st.session_state.get("missing_rpc"):
    exc=RuntimeError("missing function");exc.code="PGRST202";raise exc
   if st.session_state.get("fail_table") in ("purchases","purchase_payments",self.table):
    raise RuntimeError("模擬交易拒絕，兩筆回滾")
   purchase=dict(self.payload["p_purchase"],id="new-1",created_at=date.today().isoformat())
   payment=dict(self.payload["p_first_payment"],id="new-payment",purchase_id=purchase["id"],installment_no=1)
   st.session_state.db["purchases"].append(purchase)
   st.session_state.db["purchase_payments"].append(payment)
   st.session_state.writes.append({"table":self.table,"payload":self.payload})
   if st.session_state.get("empty_table")==self.table: return SimpleNamespace(data=None)
   record={"id":purchase["id"],"purchase_id":purchase["id"],"payment_id":payment["id"]}
   if st.session_state.get("incomplete_rpc"): record.pop("payment_id")
   return SimpleNamespace(data=record)
  if st.session_state.get("fail_table")==self.table: raise RuntimeError("模擬資料庫錯誤")
  st.session_state.writes.append({"table":self.table,"payload":self.payload})
  if self.action=="rpc":
   record={"id":"termination","purchase_id":self.payload["p_purchase_id"]}
  else:
   record=dict(self.payload,id="new-"+str(len(st.session_state.writes)),created_at=date.today().isoformat())
   st.session_state.db[self.table].append(record)
  if st.session_state.get("empty_table")==self.table: return SimpleNamespace(data=[])
  return SimpleNamespace(data=[record])
class Client:
 def table(self,name): return Query(name)
 def rpc(self,name,payload): return Query(name,action="rpc",payload=payload)
def client(): return Client()
def coach_options(): return {"虛構教練":"c"}
def _excel_bytes(*_,**__): return b"mock"
role=st.session_state.get("role","admin")
me={"role":role,"id":"c" if role=="coach" else "admin","display_name":"虛構教練"}
if st.session_state.get("selected_tab"):
 st.session_state["purchase_installment_tab"]=st.session_state["selected_tab"]
if st.session_state.get("direct_termination"):
 course_termination_report_page(me)
else:
 purchase_page(me)
'''


class PurchaseUITests(unittest.TestCase):
    def app(self, role="admin", tab=None, direct=False):
        app=AppTest.from_string("APP_PATH="+repr(str(ROOT/"app.py"))+"\n"+SCRIPT,default_timeout=20)
        app.session_state["role"]=role
        if tab: app.session_state["selected_tab"]=tab
        if direct: app.session_state["direct_termination"]=True
        app.run();self.clean(app)
        return app

    def clean(self, app):
        self.assertEqual(len(app.exception),0)

    def widget(self, app, kind, label):
        return next(x for x in getattr(app,kind) if x.label==label)

    def fill_purchase(self, app, plan="未分期"):
        self.widget(app,"selectbox","客戶姓名").set_value("虛構客戶｜000")
        self.widget(app,"selectbox","付款方式").set_value(plan)
        self.widget(app,"selectbox","課程名稱").set_value("訓練｜測試課程")
        app.run();self.clean(app)
        self.widget(app,"selectbox","購買類型").set_value("首次購買")
        self.widget(app,"number_input","課程堂數").set_value(10)
        self.widget(app,"number_input","成交總金額").set_value(10500)
        self.widget(app,"date_input","購買日期").set_value(date.today())
        self.widget(app,"date_input","有效日期").set_value(date.today()+timedelta(days=365))
        if plan=="分期":
            self.widget(app,"selectbox","總期數").set_value(3)
            self.widget(app,"number_input","此次支付金額").set_value(1050)
            self.widget(app,"date_input","支付日期").set_value(date.today())

    def fill_payment(self, app, no="第 2 期", amount=1050):
        self.widget(app,"selectbox","購買紀錄").set_value(self.widget(app,"selectbox","購買紀錄").options[0])
        app.run();self.clean(app)
        self.widget(app,"selectbox","期次").set_value(no)
        self.widget(app,"number_input","支付金額").set_value(amount)
        self.widget(app,"date_input","付款日期").set_value(date.today())

    def fill_termination(self, app, kind="退費中止"):
        self.widget(app,"selectbox","選擇會員課程").set_value(self.widget(app,"selectbox","選擇會員課程").options[0])
        app.segmented_control[0].set_value(kind).run();self.clean(app)
        self.widget(app,"date_input","中止日期").set_value(date.today())
        self.widget(app,"text_input","中止原因").set_value("虛構原因")
        self.widget(app,"text_area","備註").set_value("虛構中止備註")

    def submit(self, app, label):
        self.widget(app,"button",label).click().run();self.clean(app)

    def assert_purchase_blank(self, app):
        for label in ["客戶姓名","付款方式","課程名稱","購買類型","指導教練"]:
            self.assertIsNone(self.widget(app,"selectbox",label).value)
        for label in ["課程堂數","每堂課時數","成交總金額"]:
            self.assertIsNone(self.widget(app,"number_input",label).value)
        for label in ["購買日期","有效日期"]:
            self.assertIsNone(self.widget(app,"date_input",label).value)
        self.assertEqual(self.widget(app,"text_input","醫生轉介").value,"")
        self.assertEqual(self.widget(app,"text_area","備註").value,"")

    def test_admin_tabs_only_compute_selected_purchase(self):
        app=self.app()
        self.assertEqual([x.label for x in app.tabs],["課程購買","登錄後續期款","課程中止"])
        self.assertIn("course_catalog",app.session_state["reads"])
        self.assertNotIn("purchase_balances",app.session_state["reads"])
        self.assertNotIn("course_terminations",app.session_state["reads"])
        self.assert_purchase_blank(app)

    def test_nonadmin_tabs_and_direct_termination_guard(self):
        for role in ["coach","shared_coach","manager"]:
            with self.subTest(role=role):
                app=self.app(role)
                self.assertEqual([x.label for x in app.tabs],["課程購買","登錄後續期款"])
                blocked=self.app(role,direct=True)
                self.assertEqual(blocked.session_state["reads"],[])
                self.assertEqual(blocked.session_state["writes"],[])
                self.assertEqual(len(blocked.warning),1)

    def test_full_purchase_success_clears_all_and_keeps_other_state(self):
        app=self.app();app.session_state["payment_form_revision"]=8
        self.fill_purchase(app)
        self.assertEqual(self.widget(app,"selectbox","指導教練").value,"虛構教練")
        self.assertEqual(self.widget(app,"text_input","醫生轉介").value,"測試轉介")
        self.submit(app,"確認並建立購買紀錄")
        self.assert_purchase_blank(app)
        self.assertEqual(app.session_state["payment_form_revision"],8)
        self.assertEqual(len(app.success),1)
        writes=app.session_state["writes"]
        self.assertEqual([x["table"] for x in writes],["create_purchase_with_first_payment"])
        self.assertEqual(writes[0]["payload"]["p_first_payment"]["amount"],10500)
        self.assertEqual(app.session_state.db["purchase_payments"][-1]["purchase_id"],"new-1")
        self.assertNotIn("created_by",writes[0]["payload"]["p_purchase"])

    def test_installment_first_payment_keeps_purchase_id_and_clears(self):
        app=self.app();self.fill_purchase(app,"分期")
        self.submit(app,"確認並建立購買紀錄")
        self.assert_purchase_blank(app)
        writes=app.session_state["writes"]
        self.assertEqual(len(writes),1)
        self.assertEqual(writes[0]["payload"]["p_purchase"]["installment_count"],3)
        self.assertEqual(app.session_state.db["purchase_payments"][-1]["installment_no"],1)
        self.assertEqual(writes[0]["payload"]["p_first_payment"]["amount"],1050)
        self.assertEqual(app.session_state.db["purchase_payments"][-1]["purchase_id"],"new-1")

    def test_purchase_validation_keeps_input(self):
        app=self.app();self.fill_purchase(app)
        self.widget(app,"date_input","購買日期").set_value(None)
        self.submit(app,"確認並建立購買紀錄")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(self.widget(app,"number_input","成交總金額").value,10500)
        self.assertEqual(self.widget(app,"text_area","備註").value,"測試備註")
        self.assertEqual(len(app.error),1)

    def test_purchase_database_failure_keeps_input(self):
        app=self.app();self.fill_purchase(app);app.session_state["fail_table"]="purchases"
        self.submit(app,"確認並建立購買紀錄")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(self.widget(app,"number_input","課程堂數").value,10)
        self.assertEqual(len(app.error),1)

    def test_first_payment_failure_rolls_back_both_without_clearing(self):
        app=self.app();self.fill_purchase(app);app.session_state["fail_table"]="purchase_payments"
        self.submit(app,"確認並建立購買紀錄")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(len(app.session_state.db["purchases"]),1)
        self.assertEqual(len(app.session_state.db["purchase_payments"]),1)
        self.assertEqual(len(app.warning),1)
        self.assertIn("兩筆都不會建立",app.warning[0].value)
        self.assertEqual(self.widget(app,"number_input","成交總金額").value,10500)

    def test_missing_atomic_rpc_never_falls_back_to_separate_inserts(self):
        app=self.app();self.fill_purchase(app);app.session_state["missing_rpc"]=True
        self.submit(app,"確認並建立購買紀錄")
        self.assertEqual(app.session_state["writes"],[])
        self.assertIn("升級 SQL",app.error[0].value)
        self.assertEqual(self.widget(app,"number_input","成交總金額").value,10500)

    def test_unknown_atomic_reply_keeps_input_and_never_auto_retries(self):
        for flag in ["empty_table","incomplete_rpc"]:
            app=self.app();self.fill_purchase(app)
            app.session_state[flag]="create_purchase_with_first_payment" if flag=="empty_table" else True
            self.submit(app,"確認並建立購買紀錄")
            self.assertEqual(len(app.success),0)
            self.assertEqual(len(app.session_state.db["purchases"]),2)
            self.assertEqual(len(app.session_state.db["purchase_payments"]),2)
            self.assertEqual(self.widget(app,"number_input","成交總金額").value,10500)
            self.assertIn("勿直接重送",app.warning[0].value)
            app.run();self.clean(app)
            self.assertEqual(len(app.session_state["writes"]),1)

    def test_payment_tab_does_not_read_purchase_form_catalog(self):
        app=self.app(tab="登錄後續期款")
        self.assertNotIn("members",app.session_state["reads"])
        self.assertNotIn("course_catalog",app.session_state["reads"])
        self.assertNotIn("course_terminations",app.session_state["reads"])

    def test_payment_success_clears_all_and_keeps_same_purchase(self):
        app=self.app(tab="登錄後續期款");self.fill_payment(app)
        self.submit(app,"新增付款")
        self.assertIsNone(self.widget(app,"selectbox","購買紀錄").value)
        self.assertIsNone(self.widget(app,"selectbox","期次").value)
        self.assertIsNone(self.widget(app,"number_input","支付金額").value)
        self.assertIsNone(self.widget(app,"date_input","付款日期").value)
        self.assertEqual(app.session_state["writes"][0]["payload"]["purchase_id"],"p")
        self.assertEqual(len(app.success),1)

    def test_payment_duplicate_or_overpayment_does_not_clear_or_write(self):
        for amount,duplicate in [(10000,False),(1050,True)]:
            with self.subTest(amount=amount,duplicate=duplicate):
                app=self.app(tab="登錄後續期款");self.fill_payment(app,amount=amount)
                if duplicate:
                    app.session_state.db["purchase_payments"].append({"id":"second","purchase_id":"p","installment_no":2,"amount":1050})
                self.submit(app,"新增付款")
                self.assertEqual(app.session_state["writes"],[])
                self.assertEqual(self.widget(app,"number_input","支付金額").value,amount)
                self.assertEqual(len(app.error),1)

    def test_payment_failure_or_empty_confirmation_keeps_input(self):
        for flag in ["fail_table","empty_table"]:
            app=self.app(tab="登錄後續期款");self.fill_payment(app)
            app.session_state[flag]="purchase_payments";self.submit(app,"新增付款")
            self.assertEqual(self.widget(app,"number_input","支付金額").value,1050)
            self.assertEqual(len(app.error),1)
            self.assertEqual(len(app.success),0)

    def test_coach_payment_past_date_rejected(self):
        app=self.app(role="coach",tab="登錄後續期款");self.fill_payment(app)
        self.widget(app,"date_input","付款日期").set_value(date.today()-timedelta(days=1))
        self.submit(app,"新增付款")
        self.assertEqual(app.session_state["writes"],[])
        # 日期元件先將範圍外日期轉為空白，仍必須擋下寫入。
        self.assertIn("付款日期",app.error[0].value)
        source=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn('if me["role"]=="coach" and pay_date<date.today():',source)

    def test_coach_payment_today_success_and_no_repeat_on_rerun(self):
        app=self.app(role="coach",tab="登錄後續期款");self.fill_payment(app)
        self.submit(app,"新增付款")
        self.assertEqual(len(app.session_state["writes"]),1)
        self.assertIsNone(self.widget(app,"date_input","付款日期").value)
        app.run();self.clean(app)
        self.assertEqual(len(app.session_state["writes"]),1)

    def test_incomplete_payment_does_not_write_or_clear(self):
        app=self.app(tab="登錄後續期款");self.fill_payment(app)
        self.widget(app,"selectbox","期次").set_value(None)
        self.submit(app,"新增付款")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(self.widget(app,"number_input","支付金額").value,1050)

    def test_refund_termination_success_resets_all_controls(self):
        app=self.app(tab="課程中止");self.fill_termination(app)
        self.widget(app,"checkbox","收取剩餘金額 20% 手續費").set_value(True)
        self.submit(app,"確認中止課程")
        self.assertIsNone(self.widget(app,"selectbox","選擇會員課程").value)
        self.assertIsNone(app.segmented_control[0].value)
        self.assertIsNone(self.widget(app,"date_input","中止日期").value)
        self.assertEqual(self.widget(app,"text_input","中止原因").value,"")
        self.assertEqual(self.widget(app,"text_area","備註").value,"")
        self.assertEqual(len(app.success),1)
        payload=app.session_state["writes"][0]["payload"]
        self.assertEqual(payload["p_purchase_id"],"p")
        self.assertTrue(payload["p_charge_fee"])
        self.assertFalse(payload["p_completion_bonus_eligible"])
        self.assertEqual(payload["p_termination_type"],"refund")

    def test_expiry_bonus_still_requires_coach(self):
        app=self.app(tab="課程中止");self.fill_termination(app,"逾期中止")
        self.widget(app,"checkbox","計算結單獎金").set_value(True).run()
        self.submit(app,"確認中止課程")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(self.widget(app,"text_input","中止原因").value,"虛構原因")
        self.assertIn("歸屬教練",app.error[0].value)

    def test_termination_database_failure_keeps_inputs(self):
        app=self.app(tab="課程中止");self.fill_termination(app);app.session_state["fail_table"]="terminate_course"
        self.submit(app,"確認中止課程")
        self.assertEqual(self.widget(app,"text_area","備註").value,"虛構中止備註")
        self.assertEqual(app.segmented_control[0].value,"退費中止")
        self.assertEqual(len(app.error),1)
        self.assertEqual(app.session_state["writes"],[])

    def test_expiry_termination_with_bonus_clears_and_keeps_history_dates(self):
        app=self.app(tab="課程中止");self.fill_termination(app,"逾期中止")
        self.widget(app,"checkbox","計算結單獎金").set_value(True).run()
        self.widget(app,"selectbox","結單獎金歸屬教練").set_value("虛構教練")
        history_start=self.widget(app,"date_input","開始日期").value
        self.submit(app,"確認中止課程")
        payload=app.session_state["writes"][0]["payload"]
        self.assertEqual(payload["p_termination_type"],"expired")
        self.assertTrue(payload["p_completion_bonus_eligible"])
        self.assertEqual(payload["p_completion_bonus_coach_id"],"c")
        self.assertIsNone(app.segmented_control[0].value)
        self.assertEqual(self.widget(app,"date_input","開始日期").value,history_start)
        app.run();self.clean(app)
        self.assertEqual(len(app.session_state["writes"]),1)

    def test_unconfirmed_termination_does_not_clear(self):
        app=self.app(tab="課程中止");self.fill_termination(app)
        app.session_state["empty_table"]="terminate_course"
        self.submit(app,"確認中止課程")
        self.assertEqual(len(app.success),0)
        self.assertEqual(self.widget(app,"text_input","中止原因").value,"虛構原因")
        self.assertIn("勿直接重送",app.error[0].value)

    def test_sidebar_and_route_use_purchase_installment(self):
        source=(ROOT/"app.py").read_text(encoding="utf-8")
        sidebar=source[source.index("user=login(); me=profile(user.id)"):]
        self.assertIn('"購買及分期":purchase_page',sidebar)
        self.assertIn('"購買及分期"',sidebar)
        self.assertNotIn('"課程購買":purchase_page',sidebar)


if __name__=="__main__":
    unittest.main()
