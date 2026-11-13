"""v47 合成資料測試，沒有正式資料庫連線。"""
from datetime import timedelta
from decimal import Decimal
import unittest

from course_query_views import business_today
from streamlit.testing.v1 import AppTest
from termination_preview import preview_termination
from termination_reporting import effective_terminations, termination_events
import test_confirmed_queries as query_testing


class MoneyAndDates(unittest.TestCase):
    def test_refund_net_keeps_saved_tail(self):
        self.assertEqual(preview_termination('104.99', '99', 'refund', True), (99,20,79))
        self.assertEqual(preview_termination(105, 99, 'refund', False), (99,0,99))
        self.assertEqual(preview_termination(105, 99, 'expired', True), (99,0,0))
        for amount,net in [(0,0),(105,-1),(105,'NaN'),(105,'9.5')]:
            with self.subTest(net=net), self.assertRaises(ValueError):
                preview_termination(amount,net,'refund',True)

    def test_correction_keeps_history_and_posts_both_events_together(self):
        from test_termination_reversal import samples
        old,rev=samples()
        new=dict(old,id='new',termination_date='2026-09-29',reversed_at=None,
                 corrects_termination_id=old['id'],correction_posted_on='2026-10-15')
        rows=[new,old]
        self.assertEqual(effective_terminations(rows,'2026-09-29'),[])
        self.assertEqual(effective_terminations(rows,'2026-10-14'),[old])
        self.assertEqual(effective_terminations(rows,'2026-10-15'),[new])
        self.assertEqual(len(termination_events(rows,[rev],'2026-09-30')),1)
        changes=[r for r in termination_events(rows,[rev],'2026-10-15') if r['termination_date']=='2026-10-15']
        self.assertEqual(len(changes),2)
        self.assertEqual(sum(Decimal(str(x['refund_net_amount'])) for x in changes),0)
        self.assertEqual(next(x for x in changes if not x['is_reversal'])['original_termination_date'],'2026-09-29')


class QueryChanges(unittest.TestCase):
    app=query_testing.QueryUITests.app

    def test_schedule_after_usage_and_not_in_finance(self):
        app=self.app('coach',role='coach',coach_query_view_usage='排班管理')
        self.assertEqual(app.segmented_control[0].options[-2:],['銷課明細查詢','排班管理'])
        self.assertIn('虛構排班入口',[x.value for x in app.caption])
        self.assertEqual(app.session_state['reads'],[])
        shared=self.app('coach',role='shared_coach')
        self.assertNotIn('排班管理',shared.segmented_control[0].options)

    def test_today_installment_filter_columns_and_totals(self):
        day=business_today(); old=str(day-timedelta(days=1))
        p={'member_id':'m','coach_id':'c','purchase_date':old,'course_name':'虛構課程',
           'total_amount':3150,'total_sessions':3,'payment_plan':'installment','installment_count':3}
        purchases=[dict(p,id=pid,purchase_code=code,**opts) for pid,code,opts in [
            ('p1','TEST-01',{}),('p2','TEST-02',{}),('p3','TEST-03',{}),('p4','TEST-04',{})]]
        payments=[{'id':f'a{i}','purchase_id':pid,'installment_no':no,'amount':1050,'paid_date':d,'payment_kind':kind}
            for i,(pid,no,d,kind) in enumerate([('p1',1,old,'installment'),('p1',2,str(day),'installment'),
                ('p1',3,str(day),'installment'),('p2',1,str(day),'installment'),('p3',2,old,'installment'),
                ('p4',2,str(day),'supplement')])]
        tables={'purchases':purchases,'purchase_payments':payments,'course_termination_events':[]}
        app=self.app(general_query_main_tab='每日預收',general_prepaid_mode='今日分期入帳',tables=tables)
        self.assertEqual(app.session_state['reads'],['profiles'])
        app.button[0].click().run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        df=app.dataframe[0].value
        self.assertEqual(df['購買_ID'].tolist(),['TEST-01'])
        self.assertEqual(df['已收金額（含稅）'].tolist(),[3150])
        self.assertEqual(df['已收金額（未稅）'].tolist(),[3000])
        self.assertEqual([x.value for x in app.metric],['$ 2,000','$ 2,100'])
        comparison=self.app(general_query_main_tab='成交總表',general_purchase_mode='會員查詢',tables=tables)
        comparison.button[0].click().run()
        self.assertFalse(comparison.exception);self.assertFalse(comparison.error)
        self.assertEqual(list(df.columns),list(comparison.dataframe[0].value.columns))


CORRECTION = '''
from types import SimpleNamespace
from copy import deepcopy
import streamlit as st
from termination_correction_ui import _edit, render_correction_controls
st.session_state.setdefault('calls',[])
st.session_state.setdefault('records',[{'id':'t1','purchase_id':'p1','termination_date':'2026-01-31','termination_type':'expired',
    'remaining_amount':2100,'remaining_net_amount':2000,'reversed_at':None}])
class Api:
 def rpc(self,name,payload): self.name=name;self.payload=deepcopy(payload);return self
 def execute(self):
  st.session_state['calls'].append((self.name,self.payload))
  st.session_state['records'][0]['reversed_at']='2026-02-01T00:00:00Z'
  if st.session_state.get('lose_once'):
   st.session_state['lose_once']=False;raise RuntimeError('lost response')
  return SimpleNamespace(data={'id':'new','reversal_id':'rev','posted_on':'2026-02-01','termination_id':'t1'})
if '_termination_reversal_success' in st.session_state: st.success(st.session_state.pop('_termination_reversal_success'))
me={'id':'admin1','role':st.session_state.get('role','admin')}
if st.session_state.get('simulate_dialog_fragment') and not st.session_state.get('_termination_correction_admin1') and not st.session_state['records'][0].get('reversed_at'):
 _edit(me,st.session_state['records'][0],'TEST-001',{},Api(),'_termination_correction_admin1')
else:
 render_correction_controls(me,st.session_state['records'],{}, {}, {'p1':'TEST-001'}, {}, Api())
'''


class CorrectionUI(unittest.TestCase):
    def test_confirmation_and_retry_same_operation_after_response_lost(self):
        app=AppTest.from_string(CORRECTION,default_timeout=30)
        app.session_state['lose_once']=True;app.run()
        app.selectbox[0].set_value('t1').run()
        app.button(key='termination_correction_open').click().run()
        # AppTest reruns the whole script, unlike the browser's dialog fragment.
        app.session_state['simulate_dialog_fragment']=True
        next(x for x in app.button if x.label=='確認更正').click().run()
        self.assertEqual(app.session_state['calls'],[])
        self.assertTrue(app.error)
        next(x for x in app.text_area if x.label=='更正原因（必填）').set_value('測試更正')
        for x in app.checkbox:
            if '已確認' in x.label:x.check()
        next(x for x in app.button if x.label=='確認更正').click().run()
        self.assertFalse(app.exception)
        app.button(key='termination_correction_retry').click().run()
        self.assertFalse(app.exception)
        calls=app.session_state['calls']
        self.assertEqual(len(calls),2);self.assertEqual(calls[0],calls[1])
        self.assertEqual(calls[0][0],'correct_course_termination')
        self.assertTrue(app.success)

    def test_coach_cannot_open_correction(self):
        app=AppTest.from_string(CORRECTION,default_timeout=30);app.session_state['role']='coach';app.run()
        self.assertFalse(app.button);self.assertEqual(app.session_state['calls'],[])
