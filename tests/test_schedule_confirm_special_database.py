"""只經既有127.0.0.1:55439測試連線驗證v32，不接受正式主機。"""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
from datetime import date
from uuid import uuid4
from test_idempotency_database import sql,actor,COACH,OTHER,ADMIN

MANAGER='00000000-0000-4000-8000-000000000099'


class ConfirmSpecialDatabaseTests(unittest.TestCase):
    counter=0
    @classmethod
    def setUpClass(cls):
        sql(f"insert into auth.users(id,email,raw_user_meta_data) values('{MANAGER}','manager99@fictitious.invalid','{{\"display_name\":\"虛構主管\"}}'::jsonb) on conflict do nothing; insert into public.profiles(id,display_name,role,active) values('{MANAGER}','虛構主管','manager',true) on conflict(id) do update set role='manager',active=true")
        latest=date.fromisoformat(sql("select greatest(coalesce(max(month_start),'2060-01-01'::date),'2060-01-01'::date) from (select month_start from public.staff_schedule_months union all select month_start from public.staff_schedule_special_months) x where month_start<date '2100-01-01'")[0])
        cls.base=latest.year*12+latest.month-1;cls.counter=0
    def setUp(self):
        type(self).counter+=1;n=type(self).counter
        year,month=divmod(self.base+n,12);self.month=f'{year:04d}-{month+1:02d}-01'
    def rev(self):return int(sql(f"select coalesce((select revision from public.staff_schedule_months where coach_id='{COACH}' and month_start='{self.month}'),0)")[0])
    def query(self,action,payload=None,rev=None,token=None):
        body=json.dumps(payload or {}).replace("'","''")
        name='staff_schedule_manager_confirm' if action=='manager_confirm' else 'staff_schedule_command'
        return f"select public.{name}('{token or uuid4()}','{COACH}','{self.month}',{self.rev() if rev is None else rev},'{action}','{body}'::jsonb)"
    def send(self,action,payload=None,who=COACH,**kw):return json.loads(actor(self.query(action,payload,**kw),who))
    def fill(self):self.send('apply',{'base_shift':'A'})
    def special_query(self,action='save',rev=0,token=None,**kw):
        body={'date_from':self.month,'date_to':self.month,'kind':'typhoon','label':'虛構特殊假別','deduct_units':0,'reason':'虛構測試'}
        body.update(kw);encoded=json.dumps(body).replace("'","''")
        return f"select public.staff_schedule_special_save('{token or uuid4()}','{self.month}',{rev},'{action}','{encoded}'::jsonb)"
    def test_coach_finalization_is_db_locked_even_after_return_and_replay_safe(self):
        self.fill();query=self.query('submit');first=json.loads(actor(query));self.assertEqual(json.loads(actor(query)),first)
        for action,payload in [('save',{'work_date':self.month,'shift_code':'B'}),('withdraw',{}),('apply',{'base_shift':'B'}),('default',{'base_shift':'B'})]:
            with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'只有主管'):self.send(action,payload)
        self.send('return',{'reason':'測試退回'},who=MANAGER)
        with self.assertRaisesRegex(RuntimeError,'只有主管'):self.send('save',{'work_date':self.month,'shift_code':'B'})
        self.send('save',{'work_date':self.month,'shift_code':'B','reason':'主管修正'},who=MANAGER)
        value=json.loads(sql(f"select to_jsonb(m) from public.staff_schedule_months m where coach_id='{COACH}' and month_start='{self.month}'")[0])
        self.assertTrue(value['coach_locked']);self.assertEqual(value['finalized_by'],COACH)
    def test_admin_manager_can_complete_on_behalf_but_coach_cannot(self):
        self.fill()
        for who in (MANAGER,ADMIN):
            query=self.query('manager_confirm',{})
            result=json.loads(actor(query,who));self.assertEqual(result['state'],'approved')
            self.assertEqual(json.loads(actor(query,who)),result)
        with self.assertRaisesRegex(RuntimeError,'僅主管'):self.send('manager_confirm',{'reason':'拒絕'},who=COACH)
    def test_manager_admin_note_atomic_replay_keeps_approval_and_coach_lock(self):
        self.fill();self.send('submit');self.send('approve',who=ADMIN)
        for who in (MANAGER,ADMIN):
            note='主管備註' if who==MANAGER else '管理員備註'
            query=self.query('save',{'work_date':self.month,'shift_code':'C','start_time':'10:00','end_time':'16:00','note':note})
            first=json.loads(actor(query,who));self.assertEqual(json.loads(actor(query,who)),first)
            row=json.loads(sql(f"select to_jsonb(d) from public.staff_schedule_days d where coach_id='{COACH}' and work_date='{self.month}'")[0])
            self.assertEqual((row['shift_code'],row['start_time'],row['end_time'],row['note']),('C','10:00:00','16:00:00',note))
            self.assertEqual(first['state'],'approved')
            self.assertEqual(sql(f"select count(*) from public.staff_schedule_logs where coach_id='{COACH}' and month_start='{self.month}' and reason='{note}'")[0],'1')
        with self.assertRaisesRegex(RuntimeError,'只有主管'):self.send('save',{'work_date':self.month,'shift_code':'A'})
    def test_incomplete_confirmation_and_public_off_roll_back(self):
        with self.assertRaisesRegex(RuntimeError,'未填日期'):self.send('submit')
        with self.assertRaisesRegex(RuntimeError,'公休'):self.send('save',{'work_date':self.month,'shift_code':'public_off'})
        self.assertEqual(self.rev(),0)
    def test_legacy_status_backfill_does_not_invent_confirmation_time(self):
        rows=[json.loads(x) for x in sql("select to_jsonb(m) from public.staff_schedule_months m where month_start between '1998-01-01' and '1998-03-01' order by month_start")]
        self.assertEqual([x['coach_locked'] for x in rows],[True,True,False])
        self.assertTrue(all(x['finalized_at'] is None and x['finalized_by'] is None for x in rows))
    def test_special_manager_admin_equal_coach_anon_dml_private_denied(self):
        for who in (COACH,OTHER):
            with self.assertRaisesRegex(RuntimeError,'僅主管'):actor(self.special_query(),who)
        actor(self.special_query(),MANAGER);actor(self.special_query(rev=1,deduct_units=2),ADMIN)
        data=json.loads(actor(f"select public.staff_schedule_special_snapshot('{self.month}')",OTHER))
        self.assertEqual(data['revision'],2);self.assertEqual(data['days'][0]['deduct_units'],2)
        for query in ('delete from public.staff_schedule_special_days','update public.staff_schedule_special_months set revision=0','select * from schedule_private.special_logs'):
            with self.subTest(query=query),self.assertRaisesRegex(RuntimeError,'permission denied'):actor(query,ADMIN)
        with self.assertRaisesRegex(RuntimeError,'permission denied'):sql(f"begin;set local role anon;select public.staff_schedule_special_snapshot('{self.month}');commit;")
    def test_special_same_key_two_connections_one_write_changed_payload_rejected(self):
        query=self.special_query()
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda _:json.loads(actor(query,MANAGER)),range(2)))
        self.assertEqual(result[0],result[1])
        self.assertEqual(sql(f"select count(*) from schedule_private.special_logs where month_start='{self.month}'")[0],'1')
        with self.assertRaisesRegex(RuntimeError,'已更新'):actor(self.special_query(),MANAGER)
    def test_special_stale_two_keys_atomic(self):
        def save(_):
            try:return actor(self.special_query(),MANAGER)
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(save,range(2)))
        self.assertEqual(sum('已更新' in x for x in result),1)
    def test_special_void_replay_cancel_and_no_source_overwrite(self):
        self.fill();before=sql(f"select to_jsonb(d) from public.staff_schedule_days d where coach_id='{COACH}' and month_start='{self.month}' order by work_date")
        token=str(uuid4());query=self.special_query(token=token);first=json.loads(actor(query,MANAGER))
        with self.assertRaisesRegex(RuntimeError,'內容不同'):actor(self.special_query(token=token,label='不同'),MANAGER)
        actor(self.special_query(action='void',rev=1),MANAGER);self.assertEqual(json.loads(actor(query,MANAGER)),first)
        self.assertEqual(sql(f"select state from public.staff_schedule_special_days where work_date='{self.month}'")[0],'void')
        self.assertEqual(sql(f"select to_jsonb(d) from public.staff_schedule_days d where coach_id='{COACH}' and month_start='{self.month}' order by work_date"),before)
        key=str(uuid4());actor(f"select public.staff_schedule_operation('{key}',true)",MANAGER)
        with self.assertRaisesRegex(RuntimeError,'取消'):actor(self.special_query(rev=2,token=key),MANAGER)
    def test_special_missing_deduction_partial_or_crossmonth_rejected(self):
        for kw in ({'deduct_units':None},{'deduct_units':True},{'deduct_units':3},{'date_to':'2099-01-01'},{'start_time':'10:00','end_time':'12:00'}):
            with self.subTest(kw=kw),self.assertRaises(RuntimeError):actor(self.special_query(**kw),MANAGER)
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_special_months where month_start='{self.month}'")[0],'0')
    def test_new_security_boundaries(self):
        rows=sql("select relname||':'||relrowsecurity::text||':'||has_table_privilege('authenticated',oid,'INSERT')::text||':'||has_table_privilege('authenticated',oid,'UPDATE')::text||':'||has_table_privilege('authenticated',oid,'DELETE')::text from pg_class where oid in ('public.staff_schedule_special_days'::regclass,'public.staff_schedule_special_months'::regclass)")
        self.assertEqual(len(rows),2);self.assertTrue(all(x.endswith(':true:false:false:false') for x in rows))
        rows=sql("select proname||':'||prosecdef::text||':'||has_function_privilege('anon',oid,'EXECUTE')::text from pg_proc where pronamespace='public'::regnamespace and proname in ('staff_schedule_special_snapshot','staff_schedule_special_save','staff_schedule_manager_confirm')")
        self.assertEqual(len(rows),3);self.assertTrue(all(x.endswith(':false:false') for x in rows))


if __name__=='__main__':unittest.main()
