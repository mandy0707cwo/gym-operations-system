"""v35：額度門檻、真正草稿、原子送審及本頁預排。全部虛構資料。"""
from copy import deepcopy
from datetime import time
from pathlib import Path
import unittest
from uuid import uuid4
from streamlit.testing.v1 import AppTest
from schedule_demo_repository import DemoRepository
from schedule_allowance import DEDUCT_UNITS
from scheduling import day_payload,fill_empty
from schedule_draft import CoachDraft

ROOT=Path(__file__).resolve().parents[1];M='2026-10-01'
A={'id':'demo-a','role':'coach','display_name':'測試教練甲'}
ADMIN={'id':'demo-admin','role':'admin','display_name':'測試管理員'}


def publish(state):
    repo=DemoRepository(state,ADMIN)
    if not repo.allowance_load(M):repo.allowance_save(str(uuid4()),{'p_month':M,'p_expected_revision':0,
        'p_payload':{'holidays':[],'deduct_units':dict(DEDUCT_UNITS),'note':'虛構測試'}})


def send(repo,action,days=None,rev=None,token=None,**payload):
    if days is not None:payload['days']=days
    revision=repo.data['months'].get(('demo-a',M),{}).get('revision',0)
    return repo.command(token or str(uuid4()),{'p_coach_id':'demo-a','p_month':M,
        'p_expected_revision':revision if rev is None else rev,'p_action':action,'p_payload':payload})


class DraftRuleTests(unittest.TestCase):
    def setUp(self):self.state={};self.repo=DemoRepository(self.state,A)
    def test_unpublished_all_legacy_and_new_coach_writes_rollback(self):
        for action,p in [('save',{'work_date':M,'shift_code':'A'}),('apply',{'base_shift':'A'}),('default',{'base_shift':'A'}),('draft',{'days':[]})]:
            before=deepcopy(self.repo.data)
            with self.subTest(action=action),self.assertRaisesRegex(ValueError,'尚未核定'):send(self.repo,action,**p)
            self.assertEqual(self.repo.data,before)
    def test_partial_draft_persists_without_lock_and_replays_once(self):
        publish(self.state);token=str(uuid4());values=[day_payload(M,'full_off')]
        first=send(self.repo,'draft',values,rev=0,token=token)
        self.assertEqual(send(self.repo,'draft',values,rev=0,token=token),first)
        self.assertEqual(first['state'],'draft');self.assertEqual(len(self.repo.data['days']),1)
        self.assertEqual(len(self.repo.data['logs']),1);self.assertFalse(self.repo.data['months'][('demo-a',M)].get('coach_locked'))
        with self.assertRaisesRegex(ValueError,'不同'):send(self.repo,'draft',[],rev=0,token=token)
    def test_exact_limit_half_days_and_over_rollback(self):
        publish(self.state)
        five=[day_payload(f'2026-10-{n:02d}','full_off') for n in range(1,6)]
        send(self.repo,'draft',five);before=deepcopy(self.repo.data)
        with self.assertRaisesRegex(ValueError,'超出'):send(self.repo,'draft',[day_payload('2026-10-06','half_off','09:00','13:00')])
        self.assertEqual(self.repo.data,before)
        send(self.repo,'draft',[day_payload('2026-10-05','half_off','09:00','13:00'),day_payload('2026-10-06','half_off','09:00','13:00')])
    def test_submit_complete_atomic_locks_and_no_quota_bypass(self):
        publish(self.state);before=deepcopy(self.repo.data)
        with self.assertRaisesRegex(ValueError,'未填'):send(self.repo,'draft_submit',[day_payload(M,'A')])
        self.assertEqual(self.repo.data,before)
        full=fill_empty(M,'A',[]);result=send(self.repo,'draft_submit',full)
        self.assertEqual(result['state'],'submitted');self.assertEqual(len(self.repo.data['days']),31)
        self.assertTrue(self.repo.data['months'][('demo-a',M)]['coach_locked'])
        with self.assertRaisesRegex(ValueError,'只有主管'):send(self.repo,'draft',[])
    def test_conflict_duplicate_and_invalid_day_never_partial_write(self):
        publish(self.state)
        for values in ([day_payload(M,'A')]*2,[day_payload(M,'A'),day_payload('2026-11-01','B')],
                       [day_payload(M,'A'),day_payload('2026-10-02','public_off')]):
            before=deepcopy(self.repo.data)
            with self.assertRaises(ValueError):send(self.repo,'draft',values)
            self.assertEqual(self.repo.data,before)
        send(self.repo,'draft',[])
        with self.assertRaisesRegex(ValueError,'已更新'):send(self.repo,'draft',[],rev=0)
    def test_preview_separate_actor_month_base_preserves_and_detects_stale(self):
        draft=CoachDraft(self.state,'demo-a',M,0)
        draft.stage('save',day_payload('2026-10-04','B'),[])
        draft.stage('apply',{'base_shift':'A'},[])
        self.assertFalse(self.repo.data['days']);self.assertEqual(len(draft.payload()['days']),31)
        self.assertEqual(draft.data['days']['2026-10-04']['shift_code'],'B')
        self.assertFalse(CoachDraft(self.state,'demo-b',M,0).dirty)
        self.assertFalse(CoachDraft(self.state,'demo-a','2026-11-01',0).dirty)
        self.assertTrue(CoachDraft(self.state,'demo-a',M,1).conflict)
    def test_manager_can_correct_without_monthly_quota(self):
        manager=DemoRepository(self.state,dict(ADMIN,role='manager'))
        result=send(manager,'save',work_date=M,shift_code='full_off',note='主管更正')
        self.assertEqual(result['revision'],1)


class DraftUITests(unittest.TestCase):
    def app(self,confirmed=True):
        app=AppTest.from_file(str(ROOT/'schedule_demo.py'),default_timeout=40).run()
        app.number_input[0].set_value(2026);next(x for x in app.selectbox if x.label=='月份').set_value(10);app.run()
        if confirmed:
            state={'schedule_demo_store':app.session_state['schedule_demo_store']};publish(state)
            app.session_state['schedule_demo_store']=state['schedule_demo_store'];app.run()
        self.assertFalse(app.exception);return app
    def button(self,app,label):return next(x for x in app.button if x.label==label)
    def choose(self,app,day,code):
        next(x for x in app.selectbox if x.label=='班別' and f'2026-10-{day:02d}_' in x.key).set_value(code).run()
        self.assertFalse(app.exception)
    def test_unconfirmed_disabled_calendar_apply_draft_submit(self):
        app=self.app(False)
        self.assertTrue(all(x.disabled for x in app.selectbox if x.label=='班別'))
        for label in ('套用班表','儲存草稿','確認送出'):self.assertTrue(self.button(app,label).disabled)
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
    def test_preview_not_saved_partial_draft_and_continue_edit(self):
        app=self.app();self.choose(app,1,'full_off')
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        self.button(app,'儲存草稿').click().run();self.assertFalse(app.exception)
        store=app.session_state['schedule_demo_store'];self.assertEqual(len(store['days']),1)
        self.assertEqual(store['months'][('demo-a',M)]['state'],'draft')
        self.assertFalse(next(x for x in app.selectbox if x.label=='班別').disabled)
        self.assertNotIn('確認儲存本月班表',[x.label for x in app.button])
    def test_over_limit_disables_but_can_correct_and_then_save(self):
        app=self.app()
        for d in range(1,7):self.choose(app,d,'full_off')
        self.assertTrue(self.button(app,'儲存草稿').disabled)
        self.assertTrue(self.button(app,'確認送出').disabled)
        self.assertTrue(any('超出' in x.value for x in app.error))
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        self.choose(app,6,'regular_off')
        self.assertFalse(self.button(app,'儲存草稿').disabled)
        self.button(app,'儲存草稿').click().run();self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['schedule_demo_store']['days']),6)
    def test_apply_then_submit_once_and_readonly(self):
        app=self.app();next(x for x in app.selectbox if x.label=='預設班別').set_value('A').run()
        self.button(app,'套用班表').click().run();self.assertFalse(app.exception)
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        next(x for x in app.checkbox if x.label=='已核對整月班表，確認後由主管及管理者修改').check().run()
        self.button(app,'確認送出').click().run();self.assertFalse(app.exception)
        store=app.session_state['schedule_demo_store'];self.assertEqual(len(store['days']),31)
        self.assertTrue(store['months'][('demo-a',M)]['coach_locked']);self.assertEqual(len(store['logs']),1)
        self.assertNotIn('儲存草稿',[x.label for x in app.button])
        self.assertTrue(self.button(app,'套用班表').disabled)
    def test_custom_time_added_to_preview_then_draft(self):
        app=self.app();self.choose(app,1,'C')
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        next(x for x in app.time_input if x.label=='上班時間').set_value(time(10))
        next(x for x in app.time_input if x.label=='下班時間').set_value(time(16))
        self.button(app,'加入預排').click().run();self.assertFalse(app.exception)
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        self.button(app,'儲存草稿').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['schedule_demo_store']['days'][('demo-a',M)]['start_time'],'10:00')
