from copy import deepcopy
from datetime import date
from pathlib import Path
import unittest
from uuid import uuid4
from streamlit.testing.v1 import AppTest
from schedule_demo_repository import DemoRepository
from schedule_repository import PendingSchedule
from schedule_summary import summary_frame,unavailable_rows,custom_time_rows
from scheduling import day_payload

ROOT=Path(__file__).resolve().parents[1]
COACH={'id':'demo-a','role':'coach','display_name':'甲'}
MONTH='2026-10-01'


def request(action='apply',base='B',rev=0):
    return {'p_coach_id':'demo-a','p_month':MONTH,'p_expected_revision':rev,'p_action':action,'p_payload':{'base_shift':base}}


class CompactRulesTests(unittest.TestCase):
    def test_single_apply_saves_base_fills_and_replays_once(self):
        state={};repo=DemoRepository(state,COACH);token=str(uuid4());args=request()
        first=repo.command(token,args);self.assertEqual(first,repo.command(token,args))
        self.assertEqual(first['revision'],1);self.assertEqual(repo.data['preferences']['demo-a'],'B')
        self.assertEqual(len(repo.data['days']),31);self.assertEqual(len(repo.data['logs']),1)
        self.assertEqual(repo.data['days'][('demo-a','2026-10-04')]['shift_code'],'regular_off')
        self.assertEqual(repo.data['days'][('demo-a','2026-10-01')]['shift_code'],'B')
        before=deepcopy(repo.data)
        with self.assertRaises(ValueError):repo.command(str(uuid4()),request(base='C',rev=1))
        self.assertEqual(before,repo.data)
    def test_preserves_manual_dates_and_atomic_on_failure(self):
        state={};repo=DemoRepository(state,COACH)
        repo.command(str(uuid4()),dict(request(action='save'),p_payload=day_payload('2026-10-04','A')))
        repo.command(str(uuid4()),request(rev=1))
        self.assertEqual(repo.data['days'][('demo-a','2026-10-04')]['shift_code'],'A')
        repo.command(str(uuid4()),request(base='A',rev=2))
        self.assertEqual(repo.data['days'][('demo-a','2026-10-01')]['shift_code'],'B')
        self.assertEqual(repo.data['preferences']['demo-a'],'A')
        with self.assertRaises(ValueError):repo.command(str(uuid4()),request(rev=0))
    def test_lost_reply_and_cancelled_operation_do_not_duplicate_apply(self):
        state={};repo=DemoRepository(state,COACH)
        class Lost:
            def command(self,token,args):
                result=repo.command(token,args)
                if not getattr(self,'lost',False):self.lost=True;raise TimeoutError('虛構遺失')
                return result
            def status(self,*args):return repo.status(*args)
        pending=PendingSchedule(state,Lost(),'demo-a')
        with self.assertRaises(TimeoutError):pending.send(request())
        pending.send(request());self.assertEqual(len(repo.data['logs']),1)
        token=str(uuid4());repo.status(token,True)
        with self.assertRaisesRegex(ValueError,'取消'):repo.command(token,request(rev=1))
    def test_two_header_rows_compact_marker_and_safe_detail(self):
        coaches=[{'id':'x','display_name':'[名字](https://example.com)'}]
        data={'months':[{'coach_id':'x','coach_name':'甲','month_start':MONTH,'state':'approved'}],
              'days':[dict(day_payload('2026-10-01','C','09:00','18:00'),coach_id='x',month_start=MONTH)]}
        slots=[{'coach_id':'x','work_date':'2026-10-01','start_time':a,'end_time':b,'minutes':60,
                'leave_kind':'sick','reason':'不可公開'} for a,b in [('10:00','11:00'),('13:00','14:00')]]
        frame=summary_frame(coaches,data,MONTH,slots)
        self.assertEqual(frame.columns.nlevels,2);self.assertEqual(frame[('01','週四')][0],'C班＊')
        self.assertEqual(frame[('教練','')][0],r'\[名字\]\(https\://example\.com\)')
        rows=unavailable_rows(coaches,slots)
        self.assertEqual(len(rows),2);self.assertNotIn('leave_kind',str(rows));self.assertNotIn('不可公開',str(rows))
        self.assertEqual(custom_time_rows(coaches,data)[0]['上班'],'09:00')
        empty=summary_frame([],{'months':[],'days':[]},MONTH,[])
        self.assertEqual(empty.shape,(0,32));self.assertEqual(empty.columns.nlevels,2)


class CompactUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(ROOT/'schedule_demo.py'),default_timeout=40).run()
        app.number_input[0].set_value(2026)
        next(x for x in app.selectbox if x.label=='月份').set_value(10)
        return app.run()
    def test_all_roles_have_no_audit_page_and_coach_one_button_apply(self):
        app=self.app()
        self.assertFalse(any(x.label=='儲存預設班別' for x in app.button))
        next(x for x in app.selectbox if x.label=='預設班別').set_value('B').run()
        self.assertFalse(app.session_state['schedule_demo_store']['preferences'])
        next(x for x in app.button if x.label=='套用班表').click().run();self.assertFalse(app.exception)
        store=app.session_state['schedule_demo_store'];self.assertEqual(len(store['days']),31)
        self.assertEqual(len(store['logs']),1)
        for role,actor,tab in [('測試教練甲','demo-a','我的請假'),('測試教練乙','demo-b','我的請假'),
                               ('測試主管','demo-manager','請假登錄'),('測試管理員','demo-admin','請假登錄')]:
            next(x for x in app.selectbox if x.label=='測試身分').set_value(role).run()
            self.assertFalse(any('異動紀錄' in x.label for x in app.tabs))
            app.session_state['schedule_tab_'+actor]=tab;app.run();self.assertFalse(app.exception)
            self.assertFalse(any(x.label=='請假異動紀錄' for x in app.expander))
