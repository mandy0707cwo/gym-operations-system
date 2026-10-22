from copy import deepcopy
from datetime import date,time
from pathlib import Path
import unittest
from uuid import uuid4
from streamlit.testing.v1 import AppTest
from scheduling import day_payload,approved_matrix
from schedule_leave import leave_payload,allowance_overview
from schedule_allowance import DEDUCT_UNITS
from schedule_demo_repository import DemoRepository
from schedule_leave_repository import PendingLeave

ROOT=Path(__file__).resolve().parents[1]
MONTH='2026-10-01'
ADMIN={'id':'demo-admin','display_name':'測試管理員','role':'admin'}
MANAGER={'id':'demo-manager','display_name':'測試主管','role':'manager'}
A={'id':'demo-a','display_name':'測試教練甲','role':'coach'}
B={'id':'demo-b','display_name':'測試教練乙','role':'coach'}


def seed(store):
    repo=DemoRepository(store,ADMIN)
    for me in (A,B):
        coach=DemoRepository(store,me)
        def cmd(action,payload,rev):return coach.command(str(uuid4()),{'p_coach_id':me['id'],'p_month':MONTH,'p_action':action,'p_expected_revision':rev,'p_payload':payload})
        cmd('default',{'base_shift':'A'},0);cmd('fill',{'base_shift':'A'},1);cmd('submit',{},2)
        repo.command(str(uuid4()),{'p_coach_id':me['id'],'p_month':MONTH,'p_action':'approve','p_expected_revision':3,'p_payload':{}})
    return repo


def args(**changes):
    result={'p_id':str(uuid4()),'p_coach_id':'demo-a','p_month':MONTH,'p_expected_revision':0,'p_schedule_revision':4,
        'p_action':'save','p_payload':{'work_date':'2026-10-01','leave_kind':'sick','start_time':'10:00','end_time':'11:30','reason':'虛構請假，不含醫療資料'}}
    result.update(changes);return result


class LeaveRulesTests(unittest.TestCase):
    def test_exact_time_no_cross_day_bad_dates_or_seconds(self):
        self.assertEqual(leave_payload(MONTH,args()['p_payload'])['minutes'],90)
        for patch in ({'work_date':'2026-11-01'},{'start_time':'10:00:01'},{'end_time':'09:00'},
                      {'start_time':None},{'end_time':'24:00'},{'leave_kind':'unknown'},{'reason':' '}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):leave_payload(MONTH,dict(args()['p_payload'],**patch))
    def test_role_privacy_and_no_quota_deduction(self):
        store={};repo=seed(store);request=args();repo.leave_save(str(uuid4()),request)
        self.assertEqual(DemoRepository(store,A).leave_load(MONTH)['records'][0]['minutes'],90)
        peer=DemoRepository(store,B).leave_load(MONTH)
        self.assertFalse(peer['records']);self.assertFalse(peer['logs'])
        self.assertEqual(set(peer['availability'][0]),{'coach_id','work_date','start_time','end_time','minutes'})
        with self.assertRaisesRegex(ValueError,'僅主管'):DemoRepository(store,A).leave_save(str(uuid4()),args())
        before=deepcopy(repo.load(MONTH));self.assertEqual(before,repo.load(MONTH))
        quota=repo.allowance_save(str(uuid4()),{'p_month':MONTH,'p_expected_revision':0,'p_payload':{'holidays':[],'deduct_units':DEDUCT_UNITS,'note':'測試'}})
        rows=allowance_overview(quota,repo.load(MONTH),MONTH)
        self.assertEqual(rows[0]['已排休（天）'],0)
    def test_overlap_off_hours_unapproved_and_changes_guard(self):
        store={};repo=seed(store);repo.leave_save(str(uuid4()),args())
        for patch in ({'start_time':'11:00','end_time':'12:00'},{'work_date':'2026-10-04'},
                      {'start_time':'08:00'},{'end_time':'19:00'}):
            before=deepcopy(repo.data)
            with self.subTest(patch=patch),self.assertRaises(ValueError):repo.leave_save(str(uuid4()),args(p_payload=dict(args()['p_payload'],**patch)))
            self.assertEqual(repo.data,before)
        # 接續時段不算重疊。
        repo.leave_save(str(uuid4()),args(p_payload=dict(args()['p_payload'],start_time='11:30',end_time='12:00')))
        with self.assertRaisesRegex(ValueError,'有效請假'):
            repo.command(str(uuid4()),{'p_coach_id':'demo-a','p_month':MONTH,'p_expected_revision':4,'p_action':'save',
                'p_payload':dict(day_payload('2026-10-01','full_off'),reason='虛構更正')})
        store['schedule_demo_store']['months'][('demo-a',MONTH)]['state']='returned'
        self.assertFalse(DemoRepository(store,B).leave_load(MONTH)['availability'])
        with self.assertRaisesRegex(ValueError,'核准'):repo.leave_save(str(uuid4()),args())
    def test_edit_void_stale_replay_and_lost_reply(self):
        store={};repo=seed(store);request=args();token=str(uuid4())
        first=repo.leave_save(token,request);self.assertEqual(repo.leave_save(token,request),first)
        with self.assertRaisesRegex(ValueError,'不同'):repo.leave_save(token,args())
        update=dict(request,p_expected_revision=1,p_payload=dict(request['p_payload'],leave_kind='annual',reason='修正假別'))
        repo.leave_save(str(uuid4()),update)
        with self.assertRaisesRegex(ValueError,'已更新'):repo.leave_save(str(uuid4()),update)
        void=dict(request,p_expected_revision=2,p_action='void',p_payload={'reason':'重覆登錄作廢'})
        repo.leave_save(str(uuid4()),void)
        self.assertEqual(len(repo.data['leaves']),1);self.assertEqual(len(repo.data['leave_logs']),3)
        self.assertFalse(DemoRepository(store,B).leave_load(MONTH)['availability'])
        class Lost:
            def leave_save(self,token,request):
                result=repo.leave_save(token,request)
                if not getattr(self,'lost',False):self.lost=True;raise TimeoutError('回覆遺失')
                return result
            def status(self,*values):return repo.status(*values)
        pending=PendingLeave(store,Lost(),ADMIN['id']);request=args()
        with self.assertRaises(TimeoutError):pending.send(request)
        with self.assertRaisesRegex(ValueError,'尚未確認'):pending.send(args())
        pending.send(request);self.assertEqual(len(repo.data['leave_logs']),4)
        token=str(uuid4());repo.status(token,True)
        with self.assertRaisesRegex(ValueError,'取消'):repo.leave_save(token,args())
    def test_missing_schedule_not_zero_and_duplicate_names_no_mix(self):
        store={};repo=DemoRepository(store,ADMIN)
        self.assertIsNone(allowance_overview(None,repo.load(MONTH),MONTH)[0]['已排休（天）'])
        repo=seed(store);repo.leave_save(str(uuid4()),args())
        data=repo.load(MONTH);names=[dict(x,display_name='同名') for x in data['coaches']]
        matrix=approved_matrix(names,data,MONTH,repo.leave_load(MONTH)['availability'])
        self.assertIn('不在班',matrix[0]['01 四']);self.assertNotIn('不在班',matrix[1]['01 四'])
    def test_repository_fails_closed_for_incomplete_snapshot_and_wrong_reply(self):
        from types import SimpleNamespace
        from schedule_repository import ScheduleRepository
        class API:
            def rpc(self,*a):return self
            def execute(self):return SimpleNamespace(data={'records':[],'availability':[]})
        with self.assertRaisesRegex(ValueError,'不完整'):ScheduleRepository(lambda:API(),None).leave_load(MONTH)
        class Wrong:
            def leave_save(self,token,request):return dict(id='wrong',coach_id=request['p_coach_id'],month_start=MONTH,revision=1,state='active')
        state={};pending=PendingLeave(state,Wrong(),ADMIN['id'])
        with self.assertRaisesRegex(ValueError,'不一致'):pending.send(args())
        self.assertIsNotNone(pending.data)


class LeaveUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(ROOT/'schedule_demo.py'),default_timeout=40).run()
        app.number_input[0].set_value(2026)
        next(x for x in app.selectbox if x.label=='月份').set_value(10)
        app.run();seed_store=app.session_state['schedule_demo_store']
        state={'schedule_demo_store':seed_store};seed(state)
        app.session_state['schedule_demo_store']=state['schedule_demo_store']
        self.choose(app,'測試身分','測試管理員')
        return app
    def choose(self,app,label,value):
        next(x for x in app.selectbox if x.label==label).set_value(value).run();self.assertFalse(app.exception)
    def tab(self,app,actor,label):
        if label=='已核准班表':app.session_state['schedule_summary_view_'+actor]='教練明細'
        app.session_state['schedule_tab_'+actor]=label;app.run();self.assertFalse(app.exception)
    def button(self,app,label):return next(x for x in app.button if x.label==label)
    def test_quota_confirm_overview_and_preview_not_saved(self):
        app=self.app();self.tab(app,'demo-admin','排休額度設定')
        self.assertTrue(any('尚未核定' in x.value for x in app.info))
        self.button(app,'試算額度（不儲存）').click().run()
        self.assertTrue(any('本次修改試算：5天' in x.value for x in app.info))
        self.assertFalse(app.session_state['schedule_demo_store']['allowances'])
        next(x for x in app.checkbox).check()
        self.button(app,'確認本月排休額度').click().run();self.assertFalse(app.exception)
        self.assertIn('已核定可排休 **5天**','\n'.join(x.value for x in app.markdown))
        self.assertIn('核定時間（台灣）','\n'.join(x.value for x in app.caption))
        self.assertEqual(len(app.dataframe[0].value),2)
    def test_save_modify_void_coach_readonly_and_shared_redacted(self):
        app=self.app();self.tab(app,'demo-admin','請假登錄')
        self.button(app,'確認儲存請假').click().run()
        self.assertTrue(any('勾選確認' in x.value for x in app.error))
        app.date_input[0].set_value(date(2026,10,1))
        next(x for x in app.selectbox if x.label=='假別').set_value('sick')
        app.time_input[0].set_value(time(10));app.time_input[1].set_value(time(11,30))
        next(x for x in app.text_input if x.label=='登錄／修改原因').set_value('隱私測試原因')
        app.checkbox[0].check();self.button(app,'確認儲存請假').click().run();self.assertFalse(app.exception)
        self.assertTrue(app.success);self.assertEqual(app.date_input[0].value,None)
        self.assertEqual(len(app.session_state['schedule_demo_store']['leaves']),1)
        self.choose(app,'測試身分','測試教練乙');self.tab(app,'demo-b','已核准班表')
        frame=app.table[0].value
        self.assertEqual(frame.loc[frame[('教練','')]=='測試教練甲',('01','週四')].iloc[0],'A班＊')
        self.assertNotIn('隱私測試原因',frame.to_string())
        self.assertEqual(app.dataframe[0].value['開始'][0],'10:00')
        self.assertNotIn('假別',app.dataframe[0].value.columns)
        self.tab(app,'demo-b','我的請假');self.assertFalse(app.dataframe)
        self.assertFalse(any(x.label=='確認儲存請假' for x in app.button))
        self.choose(app,'測試身分','測試教練甲');self.tab(app,'demo-a','我的請假')
        self.assertEqual(app.dataframe[0].value['假別'][0],'病假')
        self.choose(app,'測試身分','測試主管');self.tab(app,'demo-manager','請假登錄')
        options=next(x for x in app.selectbox if x.label=='新增／修改紀錄').options
        self.choose(app,'新增／修改紀錄',options[1])
        next(x for x in app.text_input if x.label=='登錄／修改原因').set_value('作廢測試')
        app.checkbox[0].check();self.button(app,'作廢所選請假').click().run();self.assertFalse(app.exception)
        self.assertEqual(next(iter(app.session_state['schedule_demo_store']['leaves'].values()))['state'],'void')
