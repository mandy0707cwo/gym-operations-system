from copy import deepcopy
from pathlib import Path
import unittest
from uuid import uuid4
from streamlit.testing.v1 import AppTest
from schedule_allowance import normalize_allowance,allowance_totals,DEDUCT_UNITS
from schedule_allowance_repository import PendingAllowance
from schedule_demo_repository import DemoRepository

MONTH='2026-10-01'
ADMIN={'id':'demo-admin','display_name':'測試管理員','role':'admin'}
PAYLOAD={'holidays':[],'deduct_units':dict(DEDUCT_UNITS),'note':'虛構測試，非正式假日日曆'}


class AllowanceRulesTests(unittest.TestCase):
    def test_saturday_four_five_leap_and_unset(self):
        self.assertEqual(normalize_allowance(MONTH,PAYLOAD)['saturday_days'],5)
        self.assertEqual(normalize_allowance('2026-02-01',PAYLOAD)['saturday_days'],4)
        self.assertEqual(normalize_allowance('2028-02-01',PAYLOAD)['saturday_days'],4)
        self.assertIsNone(allowance_totals(None,[],MONTH,'a'))
    def test_weekend_holiday_only_observed_once_and_cross_month(self):
        p=deepcopy(PAYLOAD)
        p['holidays']=[{'name':'虛構假日','original_date':'2026-10-10','observed_date':'2026-10-12'}]
        self.assertEqual(normalize_allowance(MONTH,p)['total_units'],12)
        p['holidays']=[{'name':'虛構跨月補假','original_date':'2026-01-31','observed_date':'2026-02-02'}]
        self.assertEqual(normalize_allowance('2026-02-01',p)['total_units'],10)
        with self.assertRaises(ValueError):normalize_allowance('2026-01-01',p)
    def test_invalid_duplicate_dates_or_unconfirmed_rates_rejected(self):
        for entries in ([{'name':'重複','original_date':'2026-10-10','observed_date':'2026-10-10'}],
                        [{'name':'缺日期'}],
                        [{'name':'同日','original_date':'2026-10-12','observed_date':'2026-10-12'}]*2):
            with self.subTest(entries=entries),self.assertRaises(ValueError):
                normalize_allowance(MONTH,dict(PAYLOAD,holidays=entries))
        wrong=deepcopy(PAYLOAD);wrong['deduct_units']['weekend']=2
        with self.assertRaises(ValueError):normalize_allowance(MONTH,wrong)
    def test_only_full_half_public_deduct_and_negative_not_clamped(self):
        record=normalize_allowance(MONTH,PAYLOAD)
        rows=[{'coach_id':'a','work_date':f'2026-10-{n:02d}','shift_code':code}
              for n,code in enumerate(('full_off','half_off','public_off','weekend','regular_off','other','A','B','C'),1)]
        result=allowance_totals(record,rows,MONTH,'a')
        self.assertEqual((result['used_units'],result['remaining_units']),(5,5))
        self.assertEqual(allowance_totals(record,[dict(x,shift_code='full_off') for x in rows],MONTH,'a')['remaining_units'],-8)
        with self.assertRaises(ValueError):allowance_totals(record,rows+rows[:1],MONTH,'a')
    def test_reviewer_only_replay_stale_and_cancel(self):
        store={};admin=DemoRepository(store,ADMIN)
        args={'p_month':MONTH,'p_expected_revision':0,'p_payload':deepcopy(PAYLOAD)}
        coach=DemoRepository(store,{'id':'demo-a','role':'coach','display_name':'甲'})
        with self.assertRaises(ValueError):coach.allowance_save(str(uuid4()),args)
        pending=PendingAllowance(store,admin,ADMIN['id']);reply=pending.send(args)
        self.assertEqual(reply['total_units'],10)
        self.assertEqual(coach.allowance_load(MONTH)['revision'],1)
        with self.assertRaises(ValueError):admin.allowance_save(str(uuid4()),args)
        token=str(uuid4());admin.status(token,True)
        with self.assertRaises(ValueError):admin.allowance_save(token,args)
        manager=DemoRepository(store,{'id':'demo-manager','role':'manager','display_name':'主管'})
        result=manager.allowance_save(str(uuid4()),dict(args,p_expected_revision=1))
        self.assertEqual(result['revision'],2);self.assertEqual(result['confirmed_by'],'demo-manager')
    def test_lost_reply_retries_original_once(self):
        store={};repo=DemoRepository(store,ADMIN)
        class Lost:
            def allowance_save(self,token,args):
                result=repo.allowance_save(token,args)
                if not getattr(self,'lost',False):self.lost=True;raise TimeoutError('回覆遺失')
                return result
            def status(self,*args):return repo.status(*args)
        pending=PendingAllowance(store,Lost(),ADMIN['id'])
        args={'p_month':MONTH,'p_expected_revision':0,'p_payload':deepcopy(PAYLOAD)}
        with self.assertRaises(TimeoutError):pending.send(args)
        pending.send(args)
        self.assertEqual(len(store['schedule_demo_store']['allowance_logs']),1)
    def test_original_holiday_cannot_be_counted_in_two_months(self):
        store={};repo=DemoRepository(store,ADMIN)
        first=dict(PAYLOAD,holidays=[{'name':'虛構假日','original_date':'2026-10-10','observed_date':'2026-10-12'}])
        repo.allowance_save(str(uuid4()),{'p_month':MONTH,'p_expected_revision':0,'p_payload':first})
        second=dict(PAYLOAD,holidays=[{'name':'重複補假','original_date':'2026-10-10','observed_date':'2026-11-02'}])
        with self.assertRaisesRegex(ValueError,'其他月份'):
            repo.allowance_save(str(uuid4()),{'p_month':'2026-11-01','p_expected_revision':0,'p_payload':second})


class AllowanceUITests(unittest.TestCase):
    def app(self):
        root=Path(__file__).resolve().parents[1]
        app=AppTest.from_file(str(root/'schedule_demo.py'),default_timeout=40).run()
        next(x for x in app.number_input if x.label=='年份').set_value(2026)
        next(x for x in app.selectbox if x.label=='月份').set_value(10)
        app.run();self.assertFalse(app.exception)
        return app
    def choose(self,app,label,value):
        next(x for x in app.selectbox if x.label==label).set_value(value).run();self.assertFalse(app.exception)
    def test_admin_confirms_coach_reads_and_weekend_zero(self):
        app=self.app()
        self.assertTrue(any('額度尚未設定' in x.value for x in app.caption))
        self.assertFalse(any(x.label=='排休額度設定' for x in app.tabs))
        self.choose(app,'測試身分','測試管理員')
        app.session_state['schedule_tab_demo-admin']='排休額度設定';app.run();self.assertFalse(app.exception)
        next(x for x in app.button if x.label=='確認本月排休額度').click().run()
        self.assertTrue(any('勾選' in x.value for x in app.error))
        next(x for x in app.checkbox).check()
        next(x for x in app.button if x.label=='確認本月排休額度').click().run();self.assertFalse(app.exception)
        self.choose(app,'測試身分','測試教練甲')
        text='\n'.join(x.value for x in app.markdown)
        self.assertIn('本月可排休 **5天**',text);self.assertIn('剩餘 **5天**',text)
        key=next(x.key for x in app.selectbox if x.label=='班別' and '2026-10-01_' in x.key)
        app.selectbox(key=key).set_value('full_off').run()
        self.assertIn('已排休 **1天**','\n'.join(x.value for x in app.markdown))
        # 週末已從新排班選單移除；歷史紀錄仍保留原來不扣額度的規則。
        store=app.session_state['schedule_demo_store']
        store['days'][('demo-a','2026-10-02')]={'coach_id':'demo-a','month_start':MONTH,'work_date':'2026-10-02',
            'shift_code':'weekend','start_time':None,'end_time':None,'note':'虛構歷史紀錄'}
        app.session_state['schedule_demo_store']=store
        app.run()
        self.assertIn('已排休 **1天**','\n'.join(x.value for x in app.markdown))
        self.choose(app,'測試身分','測試主管')
        self.assertTrue(any(x.label=='排休額度設定' for x in app.tabs))
    def test_manager_admin_same_tabs_and_manager_can_confirm(self):
        app=self.app();self.choose(app,'測試身分','測試管理員')
        expected=[x.label for x in app.tabs]
        self.choose(app,'測試身分','測試主管')
        self.assertEqual([x.label for x in app.tabs],expected)
        app.session_state['schedule_tab_demo-manager']='排休額度設定';app.run()
        next(x for x in app.checkbox).check()
        next(x for x in app.button if x.label=='確認本月排休額度').click().run()
        self.assertFalse(app.exception);self.assertFalse(app.error)
        self.assertEqual(app.session_state['schedule_demo_store']['allowances'][MONTH]['confirmed_by'],'demo-manager')
