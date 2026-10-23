from copy import deepcopy
from datetime import date
import unittest
from uuid import uuid4
from scheduling import *
from schedule_repository import PendingSchedule,ScheduleRepository,confirm_saved_draft
from schedule_demo_repository import DemoRepository

COACH={'id':'demo-a','role':'coach','display_name':'甲'}
ADMIN={'id':'admin','role':'admin','display_name':'管理員'}


class DraftConfirmationTests(unittest.TestCase):
    def sample(self):
        row=dict(day_payload('2026-10-01','A'),coach_id='demo-a',month_start='2026-10-01')
        data={'months':[{'coach_id':'demo-a','state':'draft','revision':1}], 'days':[row]}
        class Repo:
            def load(self,month):return deepcopy(data)
        return data,row,Repo()
    def test_partial_saved_month_can_be_draft(self):
        data,row,repo=self.sample()
        self.assertEqual(confirm_saved_draft(repo,'2026-10-01','demo-a',1,[row])['saved_days'],1)
    def test_read_failure_never_reports_saved(self):
        class Broken:
            def load(self,month):raise TimeoutError('測試讀取失敗')
        with self.assertRaises(TimeoutError):confirm_saved_draft(Broken(),'2026-10-01','demo-a',1,[])
    def test_stale_changed_content_or_submitted_rejected(self):
        for change in ('revision','content','submitted'):
            with self.subTest(change=change):
                data,row,repo=self.sample();expected=deepcopy(row)
                if change=='revision':data['months'][0]['revision']=2
                elif change=='content':data['days'][0]['shift_code']='B'
                else:data['months'][0]['state']='submitted'
                with self.assertRaises(ValueError):confirm_saved_draft(repo,'2026-10-01','demo-a',1,[expected])


class SchedulingRulesTests(unittest.TestCase):
    def test_all_nine_shift_types(self):
        for shift in SHIFT_LABELS:
            p=day_payload('2026-10-04',shift,'10:00','16:30','其他測試')
            if shift in OFF:self.assertIsNone(p['start_time'])
            elif shift in FIXED:self.assertEqual((p['start_time'],p['end_time']),FIXED[shift])
            else:self.assertEqual(p['start_time'],'10:00')
    def test_sunday_default_not_forced_and_leap_month(self):
        rows=fill_empty('2028-02-01','A',[])
        self.assertEqual(len(rows),29)
        for row in rows:
            self.assertEqual(row['shift_code'],'regular_off' if date.fromisoformat(row['work_date']).weekday()==6 else 'A')
        custom=day_payload('2026-10-04','C','10:00','13:00')
        self.assertNotIn('2026-10-04',{x['work_date'] for x in fill_empty('2026-10-01','B',[custom])})
        self.assertTrue(display_day(date(2026,10,4),None)['preview'])
    def test_invalid_custom_and_other(self):
        for shift,a,b,note in [('C',None,None,''),('half_off','17:00','09:00',''),('other',None,None,''),('C','23:00','01:00',''),('C','09:00:01','10:00','')]:
            with self.subTest(shift=shift),self.assertRaises(ValueError):day_payload('2026-10-01',shift,a,b,note)
    def test_no_cross_month_time_lock(self):
        for month in ('2020-01-01','2035-12-01'):self.assertTrue(fill_empty(month,'A',[]))
        self.assertFalse(can_edit('coach','a','a','submitted'))
        self.assertFalse(can_edit('coach','a','b','draft'))
        self.assertTrue(can_edit('manager','m','a','approved'))


class DemoWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store={};self.repo=DemoRepository(self.store,COACH)
        from test_schedule_quota_draft import publish
        publish(self.store)
    def test_other_coach_draft_visibility_and_approved_matrix(self):
        other=DemoRepository(self.store,{'id':'demo-b','role':'coach','display_name':'乙'})
        admin=DemoRepository(self.store,ADMIN)
        self.send('default',{'base_shift':'B'});self.send('fill')
        self.assertEqual(other.load('2026-10-01')['days'],[])
        self.assertEqual(other.load('2026-10-01')['preferences'],[])
        self.assertEqual(approved_matrix([],self.repo.load('2026-10-01'),'2026-10-01'),[])
        self.send('submit')
        self.assertEqual(other.load('2026-10-01')['months'],[])
        self.send('approve',repo=admin)
        view=other.load('2026-10-01')
        matrix=approved_matrix(view['coaches'],view,'2026-10-01')
        self.assertEqual(len(matrix),1);self.assertEqual(matrix[0]['04 日'],'例假')
        self.assertEqual(len(matrix[0]),32)
        self.send('return',{'reason':'請調整'},repo=admin)
        self.assertEqual(other.load('2026-10-01')['days'],[])
        self.assertEqual(approved_matrix([],self.repo.load('2026-10-01'),'2026-10-01'),[])
    def send(self,action,payload=None,repo=None,month='2026-10-01',token=None,revision=None):
        repo=repo or self.repo
        if action=='fill' and payload is None:payload={'base_shift':repo.data['preferences'].get('demo-a')}
        current=next((x for x in repo.load(month)['months'] if x['coach_id']=='demo-a'),{'revision':0})
        args={'p_coach_id':'demo-a','p_month':month,'p_expected_revision':current['revision'] if revision is None else revision,
              'p_action':action,'p_payload':payload or {}}
        return repo.command(token or str(uuid4()),args)
    def test_full_workflow_and_audit(self):
        self.send('default',{'base_shift':'B'});self.send('fill')
        self.send('save',day_payload('2026-10-04','C','10:00','13:00'))
        self.send('fill')
        sunday=next(x for x in self.repo.load('2026-10-01')['days'] if x['work_date']=='2026-10-04')
        self.assertEqual(sunday['shift_code'],'C')
        self.send('submit')
        with self.assertRaises(ValueError):self.send('fill')
        admin=DemoRepository(self.store,ADMIN)
        self.send('approve',repo=admin)
        with self.assertRaises(ValueError):self.send('withdraw')
        self.send('return',{'reason':'請調整'},repo=admin)
        with self.assertRaises(ValueError):self.send('save',day_payload('2026-10-01','full_off'))
        self.send('save',dict(day_payload('2026-10-01','full_off'),reason='主管代修'),repo=admin)
        self.assertEqual(len(self.repo.logs('2026-10-01','demo-a')),8)
    def test_bad_submit_is_atomic(self):
        before=deepcopy(self.store)
        with self.assertRaises(ValueError):self.send('submit')
        self.assertEqual(self.store,before)
    def test_pending_unknown_retry_only_once_and_cancel_tombstone(self):
        class LostReply:
            def command(_,key,args):
                result=self.repo.command(key,args)
                if not getattr(_,'lost',False):_.lost=True;raise TimeoutError('回覆遺失')
                return result
            def status(_,key,cancel=False):return self.repo.status(key,cancel)
        pending=PendingSchedule(self.store,LostReply(),COACH['id'])
        args={'p_coach_id':'demo-a','p_month':'2026-10-01','p_expected_revision':0,'p_action':'default','p_payload':{'base_shift':'A'}}
        with self.assertRaises(TimeoutError):pending.send(args)
        with self.assertRaises(ValueError):pending.send(dict(args,p_action='fill'))
        pending.send(args)
        self.assertEqual(len(self.repo.logs('2026-10-01','demo-a')),1)
        token=str(uuid4());self.repo.status(token,True)
        with self.assertRaises(ValueError):self.repo.command(token,args)


class RepositorySnapshotTests(unittest.TestCase):
    def repository(self,value):
        from types import SimpleNamespace
        calls=[]
        class Client:
            def rpc(self,name,args):
                calls.append((name,args));return SimpleNamespace(execute=lambda:SimpleNamespace(data=value))
            def table(self,*args):raise AssertionError('不可回退成分次讀取或空白假資料')
        return ScheduleRepository(lambda:Client(),lambda f:f().execute().data),calls
    def test_load_uses_one_complete_snapshot(self):
        value={'coaches':[],'months':[],'days':[],'preferences':[]}
        repo,calls=self.repository(value)
        self.assertEqual(repo.load('2026-10-01'),value)
        self.assertEqual(calls,[('staff_schedule_snapshot',{'p_month':'2026-10-01'})])
    def test_incomplete_snapshot_fails_closed(self):
        repo,_=self.repository({'coaches':[]})
        with self.assertRaisesRegex(ValueError,'回覆不完整'):repo.load('2026-10-01')
