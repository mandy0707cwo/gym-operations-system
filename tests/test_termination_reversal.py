"""撤銷中止：日期、精確沖回及確認視窗。全部使用虛構資料。"""
from copy import deepcopy
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from finance_reporting import ledger_balance,termination_money
from termination_reporting import effective_terminations,termination_events,MONEY_FIELDS,termination_label

ROOT=Path(__file__).resolve().parents[1]


def samples():
    t={'id':'t1','purchase_id':'p1','termination_date':'2026-09-30','termination_type':'refund',
       'remaining_sessions':2,'remaining_amount':1400,'recognized_amount':280,'fee_amount':280,'refund_amount':1120,
       'remaining_net_amount':1333,'recognized_net_amount':267,'fee_net_amount':267,'refund_net_amount':1066,
       'reversed_at':'2026-10-15T01:00:00+00:00','completion_bonus_eligible':False}
    r={'id':'r1','termination_id':'t1','purchase_id':'p1','reversal_date':'2026-10-15',
       'created_at':t['reversed_at'],'created_by':'a','reason':'虛構更正','original_purchase':{'id':'p1'},'bonus_rule_snapshot':None}
    return t,r


class ReportingTests(unittest.TestCase):
    def test_historical_cutoff_keeps_original_then_releases(self):
        t,r=samples()
        self.assertEqual(effective_terminations([t],'2026-09-29'),[])
        self.assertEqual(effective_terminations([t],'2026-10-14'),[t])
        self.assertEqual(effective_terminations([t],'2026-10-15'),[])
        self.assertEqual(ledger_balance(2000,667,effective_terminations([t],'2026-09-30')[0]),0)
        self.assertEqual(ledger_balance(2000,667),1333)

    def test_two_month_events_exact_saved_net_not_tax_redivision(self):
        t,r=samples();before=deepcopy(t)
        september=termination_events([t],[r],'2026-09-30')
        all_rows=termination_events([t],[r],'2026-10-31')
        self.assertEqual(len(september),1);self.assertEqual(len(all_rows),2)
        for field in MONEY_FIELDS:self.assertEqual(sum(x[field] for x in all_rows),0)
        self.assertEqual(termination_money(all_rows[1],'refund_amount','未稅'),-1066)
        self.assertEqual(termination_label(all_rows[1]),'撤銷退費中止')
        self.assertEqual(t,before)

    def test_timezone_uses_taipei_calendar_day(self):
        t,r=samples();t['reversed_at']='2026-10-14T17:00:00Z'
        self.assertEqual(effective_terminations([t],'2026-10-14'),[t])
        self.assertEqual(effective_terminations([t],'2026-10-15'),[])

    def test_multiple_cycles_only_current_cycle_effective(self):
        t,r=samples();second=dict(t,id='t2',termination_date='2026-10-20',reversed_at=None)
        self.assertEqual(effective_terminations([t,second],'2026-10-21'),[second])
        self.assertEqual(effective_terminations([t,second],'2026-10-14'),[t])

    def test_incomplete_links_duplicate_and_negative_dates_fail_closed(self):
        t,r=samples()
        for rows,revs in [([t],[]),([t],[r,r]),([t],[dict(r,purchase_id='other')])]:
            with self.assertRaises(ValueError):termination_events(rows,revs,'2026-10-31')
        with self.assertRaises(ValueError):effective_terminations([dict(t,reversed_at='2026-09-29T00:00:00Z')],'2026-10-31')
        with self.assertRaises(ValueError):effective_terminations([dict(t,reversed_at=None)]*2,'2026-10-31')


SCRIPT='''
from types import SimpleNamespace
from copy import deepcopy
import streamlit as st
from termination_reversal_ui import render_reversal_controls
st.session_state.setdefault('records',[{'id':'t1','purchase_id':'p1','termination_date':'2026-09-30','termination_type':'refund','reversed_at':None}])
st.session_state.setdefault('calls',[])
st.session_state.setdefault('receipts',{})
class Api:
 def rpc(self,name,payload):
  self.name=name;self.payload=deepcopy(payload);return self
 def execute(self):
  st.session_state['calls'].append((self.name,self.payload))
  key=self.payload['p_operation_id']
  st.session_state['receipts'].setdefault(key,{'id':'rev1','termination_id':'t1','purchase_id':'p1','restored_status':'active'})
  if st.session_state.get('lose_once'):
   st.session_state['lose_once']=False
   raise RuntimeError('虛構回應中斷')
  st.session_state['records'][0]['reversed_at']='2026-10-15T01:00:00+00:00'
  return SimpleNamespace(data=st.session_state['receipts'][key])
if '_termination_reversal_success' in st.session_state:
 st.success(st.session_state.pop('_termination_reversal_success'))
render_reversal_controls({'id':'fictional-admin','role':st.session_state.get('role','admin')},
 st.session_state['records'],{'p1':{'member_id':'m1'}},{'m1':'虛構會員'},{'p1':'TEST-001'},Api())
'''


class ReversalUITests(unittest.TestCase):
    def app(self,**state):
        app=AppTest.from_string(SCRIPT,default_timeout=40)
        for k,v in state.items():app.session_state[k]=v
        app.run();self.assertFalse(app.exception);return app

    def open(self,app):
        app.selectbox[0].set_value('t1').run()
        next(x for x in app.button if x.label=='撤銷中止').click().run()
        self.assertFalse(app.exception)

    def confirm(self,app):next(x for x in app.button if x.label=='確認撤銷').click().run()

    def test_nonadmin_no_controls_or_rpc(self):
        for role in ('coach','manager','shared_coach'):
            app=self.app(role=role);self.assertFalse(app.button);self.assertEqual(app.session_state['calls'],[])

    def test_reason_and_ack_required(self):
        app=self.app();self.open(app);self.confirm(app)
        self.assertEqual(app.session_state['calls'],[])
        app.text_area[0].set_value('虛構錯誤中止');self.confirm(app)
        self.assertEqual(app.session_state['calls'],[])

    def test_confirm_calls_only_atomic_rpc_and_removes_action(self):
        app=self.app();self.open(app)
        app.text_area[0].set_value('虛構錯誤中止');app.checkbox[0].check();self.confirm(app)
        self.assertFalse(app.exception);calls=app.session_state['calls']
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'reverse_course_termination')
        self.assertTrue(calls[0][1]['p_settlement_confirmed']);self.assertFalse(app.selectbox)
        self.assertTrue(app.success)

    def test_uncertain_response_preserves_operation_key(self):
        app=self.app(lose_once=True);self.open(app)
        app.text_area[0].set_value('虛構錯誤中止');app.checkbox[0].check();self.confirm(app)
        self.assertFalse(app.exception);self.assertTrue(app.warning)
        token=app.session_state['calls'][0][1]['p_operation_id']
        self.confirm(app);self.assertFalse(app.exception)
        calls=app.session_state['calls'];self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][1]['p_operation_id'],token);self.assertEqual(len(app.session_state['receipts']),1)
