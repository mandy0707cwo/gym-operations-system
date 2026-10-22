import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from uuid import uuid4
from test_idempotency_database import sql,actor,COACH,OTHER,ADMIN


def encoded(value):return json.dumps(value,ensure_ascii=False).replace("'","''")


class LeaveDatabaseTests(unittest.TestCase):
    def setUp(self):
        n=int(sql("select count(*) from public.staff_schedule_months where month_start>=date '2200-01-01'")[0])
        self.month=f'{2200+n//12:04d}-{n%12+1:02d}-01'
        self.day=sql(f"select min(d::date) from generate_series('{self.month}'::date,'{self.month}'::date+interval '6 days',interval '1 day') d where extract(isodow from d)<6")[0]
        self.off=sql(f"select min(d::date) from generate_series('{self.month}'::date,'{self.month}'::date+interval '6 days',interval '1 day') d where extract(isodow from d)=7")[0]
        self.command('default',{'base_shift':'A'},0)
        self.command('fill',{'base_shift':'A'},1)
        self.command('submit',{},2)
        self.command('approve',{},3,ADMIN)
        self.id=str(uuid4())
        self.payload={'work_date':self.day,'leave_kind':'sick','start_time':'10:00','end_time':'11:30','reason':'虛構私密原因'}
    def command(self,action,payload,rev,who=COACH):
        return actor(f"select public.staff_schedule_command('{uuid4()}','{COACH}','{self.month}',{rev},'{action}','{encoded(payload)}'::jsonb)",who)
    def query(self,token=None,id=None,payload=None,rev=0,action='save',schedule_rev=4):
        return f"select public.staff_schedule_leave_save('{token or uuid4()}','{id or self.id}','{COACH}','{self.month}',{rev},{schedule_rev},'{action}','{encoded(self.payload if payload is None else payload)}'::jsonb)"
    def load(self,who):return json.loads(actor(f"select public.staff_schedule_leave_snapshot('{self.month}')",who))
    def test_RLS_private_detail_safe_projection_and_direct_write_denial(self):
        for who in (COACH,OTHER):
            with self.assertRaisesRegex(RuntimeError,'僅主管'):actor(self.query(),who)
        actor(self.query(),ADMIN)
        own=self.load(COACH);peer=self.load(OTHER)
        self.assertEqual(own['records'][0]['minutes'],90);self.assertEqual(len(own['logs']),1)
        self.assertFalse(peer['records']);self.assertFalse(peer['logs'])
        self.assertEqual(set(peer['availability'][0]),{'coach_id','work_date','start_time','end_time','minutes'})
        self.assertNotIn('sick',json.dumps(peer));self.assertNotIn('虛構私密原因',json.dumps(peer,ensure_ascii=False))
        self.assertEqual(actor(f"select count(*) from public.staff_schedule_leaves where id='{self.id}'",OTHER),'0')
        for q in ('delete from public.staff_schedule_leaves','update public.staff_schedule_leaves set state=\'void\''):
            with self.assertRaisesRegex(RuntimeError,'permission denied'):actor(q,ADMIN)
        with self.assertRaisesRegex(RuntimeError,'permission denied'):sql(f"begin;set local role anon;select public.staff_schedule_leave_snapshot('{self.month}');rollback;")
    def test_concurrent_same_operation_one_audit_and_changed_payload_denied(self):
        query=self.query();before=sql('select count(*) from public.purchases')[0]
        with ThreadPoolExecutor(2) as pool:replies=list(pool.map(lambda _:json.loads(actor(query,ADMIN)),range(2)))
        self.assertEqual(replies[0],replies[1]);self.assertEqual(len(self.load(ADMIN)['logs']),1)
        self.assertEqual(sql('select count(*) from public.purchases')[0],before)
        with self.assertRaisesRegex(RuntimeError,'已更新'):actor(self.query(),ADMIN)
    def test_distinct_operations_overlap_serialized_and_touching_allowed(self):
        def save(_):
            try:return actor(self.query(id=str(uuid4())),ADMIN)
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:replies=list(pool.map(save,range(2)))
        self.assertEqual(sum('重疊' in x for x in replies),1)
        self.assertEqual(len(self.load(ADMIN)['records']),1)
        actor(self.query(id=str(uuid4()),payload=dict(self.payload,start_time='11:30',end_time='12:00')),ADMIN)
        self.assertEqual(len(self.load(ADMIN)['records']),2)
    def test_bad_times_off_schedule_bad_kind_rollback_no_false_receipt(self):
        for patch in ({'work_date':self.off},{'start_time':'08:00'},{'end_time':'19:00'},{'end_time':'09:00'},
                      {'start_time':'10:00:01'},{'end_time':'24:00'},{'leave_kind':'x'},{'reason':' '}):
            token=str(uuid4())
            with self.subTest(patch=patch),self.assertRaises(RuntimeError):actor(self.query(token,payload=dict(self.payload,**patch)),ADMIN)
            self.assertFalse(self.load(ADMIN)['records'])
            self.assertEqual(json.loads(actor(f"select public.staff_schedule_operation('{token}')",ADMIN))['state'],'not_found')
    def test_edit_void_audit_and_cancel_tombstone(self):
        token=str(uuid4());reply=json.loads(actor(self.query(token),ADMIN))
        self.assertEqual(reply['minutes'],90)
        with self.assertRaisesRegex(RuntimeError,'內容不同'):actor(self.query(token,payload=dict(self.payload,leave_kind='annual')),ADMIN)
        actor(self.query(rev=1,payload=dict(self.payload,leave_kind='annual',reason='更正假別')),ADMIN)
        self.assertEqual(self.load(COACH)['records'][0]['revision'],2)
        actor(self.query(rev=2,action='void',payload={'reason':'誤登作廢'}),ADMIN)
        loaded=self.load(ADMIN);self.assertEqual(len(loaded['logs']),3);self.assertEqual(len(loaded['records']),1)
        self.assertFalse(self.load(OTHER)['availability'])
        token=str(uuid4());actor(f"select public.staff_schedule_operation('{token}',true)",ADMIN)
        with self.assertRaisesRegex(RuntimeError,'取消'):actor(self.query(token,id=str(uuid4())),ADMIN)
    def test_schedule_changes_cannot_invalidate_leave_and_return_hides_shared(self):
        actor(self.query(),ADMIN)
        with self.assertRaisesRegex(RuntimeError,'有效請假'):
            self.command('save',{'work_date':self.day,'shift_code':'full_off','reason':'測試更正'},4,ADMIN)
        self.assertEqual(sql(f"select revision from public.staff_schedule_months where coach_id='{COACH}' and month_start='{self.month}'")[0],'4')
        self.command('return',{'reason':'退回測試'},4,ADMIN)
        self.assertFalse(self.load(OTHER)['availability']);self.assertEqual(len(self.load(COACH)['records']),1)
        with self.assertRaisesRegex(RuntimeError,'核准'):actor(self.query(id=str(uuid4())),ADMIN)
        actor(self.query(rev=1,action='void',payload={'reason':'班表調整前先作廢'}),ADMIN)
        self.command('save',{'work_date':self.day,'shift_code':'full_off','reason':'調班測試'},5,ADMIN)
    def test_manager_can_write_inactive_denied_and_service_backup_read(self):
        sql(f"update public.profiles set role='manager' where id='{OTHER}'")
        try:actor(self.query(),OTHER)
        finally:sql(f"update public.profiles set role='coach' where id='{OTHER}'")
        sql(f"update public.profiles set active=false where id='{OTHER}'")
        try:
            with self.assertRaisesRegex(RuntimeError,'權限|停用'):self.load(OTHER)
        finally:sql(f"update public.profiles set active=true where id='{OTHER}'")
        self.assertTrue(sql('begin;set local role service_role;select count(*) from public.staff_schedule_leaves;rollback;'))
    def test_concurrent_leave_and_day_change_preserve_consistency(self):
        def leave():
            try:return actor(self.query(),ADMIN)
            except RuntimeError as exc:return str(exc)
        def shift():
            try:return self.command('save',{'work_date':self.day,'shift_code':'full_off','reason':'同時改班'},4,ADMIN)
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:replies=[x.result() for x in (pool.submit(leave),pool.submit(shift))]
        invalid=sql(f"select count(*) from public.staff_schedule_leaves l join public.staff_schedule_days d using(coach_id,work_date) where l.month_start='{self.month}' and l.state='active' and (d.start_time is null or l.start_time<d.start_time or l.end_time>d.end_time)")[0]
        self.assertEqual(invalid,'0');self.assertTrue(any('有效請假' in x or '已更新' in x or '上班時段' in x for x in replies))
