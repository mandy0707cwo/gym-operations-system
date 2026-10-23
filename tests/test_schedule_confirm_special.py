"""v32整月鎖定、特殊假別、完成簡表、防重送；全部使用虛構資料。"""
from copy import deepcopy
from datetime import date
from pathlib import Path
from uuid import uuid4
import unittest
from schedule_demo_repository import DemoRepository
from scheduling import can_edit,day_payload
from schedule_special import normalize_special,active_specials,special_projection,combined_slots,progress_rows
from schedule_special_ui import PendingSpecial
from schedule_allowance import allowance_totals,normalize_allowance,DEDUCT_UNITS
from schedule_headcounts import headcounts

M='2026-10-01'
A={'id':'demo-a','role':'coach','display_name':'虛構甲'}
MAN={'id':'demo-manager','role':'manager','display_name':'虛構主管'}
ADM={'id':'demo-admin','role':'admin','display_name':'虛構管理員'}


def payload(**kw):
    return dict({'date_from':M,'date_to':M,'kind':'typhoon','label':'虛構颱風天','start_time':None,'end_time':None,'deduct_units':0,'reason':'虛構設定'},**kw)


class ConfirmSpecialTests(unittest.TestCase):
    def setUp(self):
        self.state={};self.coach=DemoRepository(self.state,A);self.manager=DemoRepository(self.state,MAN)
        self.manager.allowance_save(str(uuid4()),{'p_month':M,'p_expected_revision':0,
            'p_payload':{'holidays':[],'deduct_units':dict(DEDUCT_UNITS),'note':'虛構測試核定'}})
    def cmd(self,action,content=None,repo=None,token=None,rev=None):
        repo=repo or self.coach;m=self.state['schedule_demo_store']['months'].get(('demo-a',M),{'revision':0})
        return repo.command(token or str(uuid4()),{'p_coach_id':'demo-a','p_month':M,'p_expected_revision':m['revision'] if rev is None else rev,
            'p_action':action,'p_payload':content or {}})
    def fill(self):self.cmd('apply',{'base_shift':'A'})
    def special(self,who=None,action='save',token=None,rev=None,**kw):
        repo=who or self.manager
        return repo.special_save(token or str(uuid4()),{'p_month':M,'p_expected_revision':repo.special_load(M)['revision'] if rev is None else rev,
            'p_action':action,'p_payload':payload(**kw)})
    def test_confirmed_month_coach_cannot_edit_withdraw_or_return_unlock(self):
        self.fill();token=str(uuid4());rev=1;first=self.cmd('submit',token=token,rev=rev)
        self.assertEqual(self.cmd('submit',token=token,rev=rev),first)
        for action,content in [('save',day_payload(M,'B')),('apply',{'base_shift':'B'}),('withdraw',{}),('default',{'base_shift':'B'})]:
            before=deepcopy(self.state)
            with self.assertRaisesRegex(ValueError,'只有主管'):self.cmd(action,content)
            self.assertEqual(self.state,before)
        self.cmd('return',{'reason':'虛構退回'},repo=self.manager)
        with self.assertRaisesRegex(ValueError,'只有主管'):self.cmd('save',day_payload(M,'B'))
        self.cmd('save',dict(day_payload(M,'B'),reason='主管更正'),repo=self.manager)
        self.assertFalse(can_edit('coach','demo-a','demo-a','returned',True))
    def test_manager_and_admin_can_fill_finalize_and_preserve_lock(self):
        self.fill()
        for me in (MAN,ADM):
            repo=DemoRepository(self.state,me)
            self.cmd('manager_confirm',{'reason':'代填完成'},repo=repo)
            self.assertTrue(self.manager.load(M)['months'][0]['coach_locked'])
            self.assertEqual(self.manager.load(M)['months'][0]['state'],'approved')
        with self.assertRaises(ValueError):self.cmd('manager_confirm',{'reason':'非主管'})
    def test_public_off_only_reviewers(self):
        with self.assertRaisesRegex(ValueError,'公休'):self.cmd('save',day_payload(M,'public_off'))
        self.cmd('save',dict(day_payload(M,'public_off'),reason='主管代排'),repo=self.manager)
    def test_special_roles_required_deduction_validation_and_range(self):
        with self.assertRaises(ValueError):self.special(who=self.coach)
        for kw in ({'deduct_units':None},{'deduct_units':True},{'deduct_units':3},{'date_to':'2026-11-01'},{'start_time':'18:00','end_time':'12:00'}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):normalize_special(M,payload(**kw))
        self.special();self.assertEqual(len(self.manager.special_load(M)['days']),1)
    def test_special_projection_zero_deduction_preserves_original_and_void_restores(self):
        self.fill();self.cmd('save',day_payload(M,'full_off'));before=self.manager.load(M)
        self.special();events=active_specials(self.manager.special_load(M),M)
        projected=special_projection(before,events)
        row=next(x for x in projected['days'] if x['work_date']==M)
        self.assertEqual(row['special_deduct_units'],0);self.assertEqual(row['shift_code'],'public_off')
        allowance=normalize_allowance(M,{'holidays':[],'deduct_units':DEDUCT_UNITS})
        self.assertEqual(allowance_totals(allowance,projected['days'],M,'demo-a')['used_units'],0)
        self.assertEqual(self.manager.load(M),before)
        self.special(action='void')
        self.assertEqual(special_projection(before,active_specials(self.manager.special_load(M),M)),before)
    def test_special_and_leave_union_no_duplicate_minutes(self):
        self.fill();self.cmd('submit');self.cmd('approve',repo=self.manager)
        self.special(kind='banquet',label='虛構尾牙',deduct_units=1)
        events=active_specials(self.manager.special_load(M),M);data=self.manager.load(M)
        slots=combined_slots(data,[{'coach_id':'demo-a','work_date':M,'start_time':'14:00','end_time':'17:00','minutes':180}],events)
        self.assertEqual(len(slots),1);self.assertEqual(slots[0]['minutes'],540)
        self.assertEqual(slots[0]['start_time'],'09:00');self.assertEqual(slots[0]['end_time'],'18:00')
        result=headcounts(data['coaches'],data,M,slots)
        self.assertEqual(result['rows'][0]['cells'][0]['text'],'0/1')
    def test_full_special_availability_zero_original_count_kept(self):
        self.fill();self.cmd('submit');self.cmd('approve',repo=self.manager);self.special()
        data=self.manager.load(M);events=active_specials(self.manager.special_load(M),M)
        result=headcounts(data['coaches'],data,M,combined_slots(data,[],events))
        self.assertEqual(result['rows'][0]['cells'][0]['text'],'0/1')
    def test_full_special_also_zeros_other_without_known_work_hours(self):
        self.fill();self.cmd('save',day_payload(M,'other',note='尚未定時段'))
        self.cmd('submit');self.cmd('approve',repo=self.manager);self.special()
        data=self.manager.load(M);events=active_specials(self.manager.special_load(M),M)
        result=headcounts(data['coaches'],special_projection(data,events,for_headcount=True),M,combined_slots(data,[],events))
        self.assertEqual(result['rows'][2]['cells'][0]['text'],'0/1')
    def test_special_labels_are_safe_in_shared_table_and_excel(self):
        from schedule_summary import summary_frame
        from scheduling import export_rows
        self.fill();self.cmd('submit');self.cmd('approve',repo=self.manager)
        self.special(label='=1+1 [顯示](example)')
        data=special_projection(self.manager.load(M),active_specials(self.manager.special_load(M),M))
        frame=summary_frame(data['coaches'],data,M,[])
        self.assertIn('\\[顯示\\]',frame.iloc[0,1])
        self.assertTrue(export_rows(data['coaches'],data['months'],data['days'])[0]['班別'].startswith("'="))
    def test_progress_requires_confirmation_not_just_filled_days(self):
        self.fill();data=self.manager.load(M)
        rows=progress_rows(MAN,data,M,{'demo-a':'smc001','demo-b':'smc002'})
        self.assertEqual([x['排休進度'] for x in rows],['未完成','未完成'])
        self.cmd('submit');rows=progress_rows(MAN,self.manager.load(M),M,{'demo-a':'smc001'})
        self.assertEqual(rows[0]['排休進度'],'已完成');self.assertEqual(rows[0]['班表狀態'],'待審')
        self.assertEqual(rows[1]['尚未填寫（天）'],31)
        with self.assertRaises(ValueError):progress_rows(A,data,M,{})
    def test_special_replay_stale_and_cancel_tombstone(self):
        token=str(uuid4());first=self.special(token=token,rev=0)
        self.assertEqual(self.special(token=token,rev=0),first)
        with self.assertRaisesRegex(ValueError,'不同'):self.special(token=token,rev=0,label='不同內容')
        with self.assertRaisesRegex(ValueError,'更新'):self.special(rev=0)
        key=str(uuid4());self.manager.status(key,True)
        with self.assertRaisesRegex(ValueError,'取消'):self.special(token=key)
        self.assertEqual(len(self.manager.data['special_logs']),1)
    def test_special_lost_reply_only_one_log_and_retains_pending(self):
        repo=self.manager
        class Lost:
            def special_save(self,key,args):
                result=repo.special_save(key,args)
                if not getattr(self,'lost',False):self.lost=True;raise TimeoutError('模擬回覆遺失')
                return result
            def status(self,key,cancel=False):return repo.status(key,cancel)
        pending=PendingSpecial(self.state,Lost(),MAN['id'])
        args={'p_month':M,'p_expected_revision':0,'p_action':'save','p_payload':payload()}
        with self.assertRaises(TimeoutError):pending.send(args)
        self.assertTrue(pending.data);pending.send(args)
        self.assertIsNone(pending.data);self.assertEqual(len(repo.data['special_logs']),1)


if __name__=='__main__':unittest.main()
