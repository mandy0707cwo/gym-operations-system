"""以實際銷課頁與實際操作控制器驗證只扣一次及明確下一筆。"""
import unittest
from streamlit.testing.v1 import AppTest
import test_purchase_installment_ui as purchase_ui

SCRIPT=purchase_ui.SCRIPT.replace('"rows","purchase_page"','"usage_page","rows","purchase_page"')
SCRIPT=SCRIPT.replace(' def order(self,*_,**__): return self',' def limit(self,*_,**__): return self\n def order(self,*_,**__): return self')
SCRIPT=SCRIPT.replace('  if self.table in ("operation_status","cancel_operation"):', '''  if self.table=="consume_session_idempotent":
   token=(str(me["id"]),self.payload["p_operation_id"])
   receipts=st.session_state.get("test_receipts",{})
   if token in receipts: return SimpleNamespace(data=receipts[token]["result"])
   records=st.session_state.db.setdefault("session_usages",[])
   record={"id":"u"+str(len(records)+1),"purchase_id":"p","coach_id":"c","usage_date":self.payload["p_usage_date"],
           "actual_usage_date":self.payload["p_actual_usage_date"],"is_makeup":False,"session_seq":len(records)+1,
           "deducted_amount":1050,"deducted_net_amount":1000,"note":self.payload.get("p_note"),"created_at":"2026-10-18"}
   records.append(record)
   st.session_state.writes.append({"table":self.table,"payload":self.payload})
   receipts[token]={"state":"completed","result":dict(record)}
   st.session_state["test_receipts"]=receipts
   if st.session_state.get("lose_usage_reply"): raise TimeoutError("模擬回覆遺失")
   return SimpleNamespace(data=record)
  if self.table in ("operation_status","cancel_operation"):''')
SCRIPT=SCRIPT[:SCRIPT.index('if st.session_state.get("direct_catalog"):')]+'''
def localize_usage_search_no_results(): pass
def show_table(*a,**k): pass
LABELS={}
st.session_state.db["purchase_balances"][0].update(member_id="m",total_sessions=10,total_amount=10500,used_sessions=0,coach_name="虛構教練")
usage_page(me)
'''


class UsageOperationUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_string('APP_PATH='+repr(str(purchase_ui.ROOT/'app.py'))+'\n'+SCRIPT,default_timeout=30)
        app.run()
        self.assertFalse(app.exception)
        next(x for x in app.selectbox if x.label=='會員名稱').set_value('虛構客戶').run()
        self.assertFalse(app.exception)
        return app

    def test_success_and_rerun_never_consume_next_session(self):
        app=self.app()
        next(x for x in app.button if x.label=='確認扣除 1 堂').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['writes']),1)
        app.run()
        self.assertEqual(len(app.session_state['writes']),1)
        self.assertTrue(any(x.label=='登錄下一筆銷課' for x in app.button))

    def test_unknown_reply_resolves_original_without_second_usage(self):
        app=self.app()
        app.session_state['lose_usage_reply']=True
        next(x for x in app.button if x.label=='確認扣除 1 堂').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['writes']),1)
        next(x for x in app.button if x.label=='查核原操作結果').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['writes']),1)
        self.assertEqual(app.session_state['_operation_usage']['state'],'completed')
