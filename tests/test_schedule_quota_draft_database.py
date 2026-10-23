"""固定localhost:55439虛構庫；新規則、越權、防重送與原子交易測試。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import unittest
from uuid import uuid4
from test_idempotency_database import sql,actor,COACH,OTHER,ADMIN
from scheduling import fill_empty,day_payload
from schedule_allowance import DEDUCT_UNITS


class QuotaDraftDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        latest=date.fromisoformat(sql("select greatest(coalesce(max(month_start),'2200-01-01'::date),'2200-01-01'::date) from public.staff_schedule_months where month_start<date '2300-01-01'")[0])
        cls.base=latest.year*12+latest.month-1;cls.seq=0
    def setUp(self):
        type(self).seq+=1;y,m=divmod(self.base+self.seq,12);self.month=f'{y:04d}-{m+1:02d}-01'
    def rev(self):return int(sql(f"select coalesce((select revision from public.staff_schedule_months where coach_id='{COACH}' and month_start='{self.month}'),0)")[0])
    def query(self,action,payload=None,rev=None,token=None,coach=COACH):
        body=json.dumps(payload or {},ensure_ascii=False).replace("'","''")
        return f"select public.staff_schedule_command('{token or uuid4()}','{coach}','{self.month}',{self.rev() if rev is None else rev},'{action}','{body}'::jsonb)"
    def send(self,action,payload=None,who=COACH,**kw):return json.loads(actor(self.query(action,payload,**kw),who))
    def publish(self,holidays=None,revision=0):
        body=json.dumps({'holidays':holidays or [],'deduct_units':DEDUCT_UNITS,'note':'虛構核定'}).replace("'","''")
        return json.loads(actor(f"select public.staff_schedule_allowance_save('{uuid4()}','{self.month}',{revision},'{body}'::jsonb)",ADMIN))
    def values(self,n,code='full_off'):
        return [day_payload(self.month[:8]+f'{i:02d}',code) for i in range(1,n+1)]
    def count(self,table):return int(sql(f"select count(*) from public.{table} where month_start='{self.month}'")[0])
    def test_unconfirmed_old_new_endpoints_rollback_and_manager_exempt(self):
        for action,payload in [('draft',{'days':[]}),('save',dict(work_date=self.month,shift_code='A')),('apply',{'base_shift':'A'}),('default',{'base_shift':'A'})]:
            with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'尚未核定'):self.send(action,payload)
            self.assertEqual(self.rev(),0);self.assertEqual(self.count('staff_schedule_days'),0)
        self.send('apply',{'base_shift':'A'},who=ADMIN)
        with self.assertRaisesRegex(RuntimeError,'尚未核定'):self.send('submit')
        self.assertEqual(sql(f"select state from public.staff_schedule_months where month_start='{self.month}'")[0],'draft')
    def test_partial_save_unlocked_and_legacy_over_limit_blocked(self):
        quota=self.publish();self.send('draft',{'days':[day_payload(self.month,'A')]})
        self.assertEqual(self.count('staff_schedule_days'),1)
        self.assertEqual(sql(f"select coach_locked::text from public.staff_schedule_months where month_start='{self.month}'")[0],'false')
        n=quota['total_units']//2
        self.send('draft',{'days':self.values(n)})
        before=self.rev()
        with self.assertRaisesRegex(RuntimeError,'超出'):self.send('save',dict(work_date=self.month[:8]+f'{n+1:02d}',shift_code='full_off'))
        self.assertEqual(self.rev(),before);self.assertEqual(self.count('staff_schedule_days'),n)
    def test_excess_batch_reverts_all_days_preferences_revision_and_logs(self):
        quota=self.publish();before=self.count('staff_schedule_logs')
        with self.assertRaisesRegex(RuntimeError,'超出'):
            self.send('draft',{'days':self.values(quota['total_units']//2+1),'base_shift':'B'})
        self.assertEqual(self.rev(),0);self.assertEqual(self.count('staff_schedule_days'),0)
        self.assertEqual(self.count('staff_schedule_logs'),before)
    def test_submit_atomic_missing_rolls_back_complete_locks(self):
        self.publish()
        with self.assertRaisesRegex(RuntimeError,'未填'):self.send('draft_submit',{'days':[day_payload(self.month,'A')]})
        self.assertEqual(self.rev(),0)
        result=self.send('draft_submit',{'days':fill_empty(self.month,'A',[]),'base_shift':'A'})
        self.assertEqual(result['state'],'submitted');self.assertEqual(self.count('staff_schedule_days'),len(fill_empty(self.month,'A',[])))
        with self.assertRaisesRegex(RuntimeError,'未鎖定'):self.send('draft',{'days':[]})
        self.send('save',dict(work_date=self.month,shift_code='B',note='主管更正'),who=ADMIN)
        self.assertEqual(sql(f"select coach_locked::text from public.staff_schedule_months where month_start='{self.month}'")[0],'true')
    def test_same_token_concurrent_replays_once_and_changed_payload_denied(self):
        self.publish();token=str(uuid4());query=self.query('draft',{'days':[day_payload(self.month,'A')]},token=token,rev=0)
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(lambda _:json.loads(actor(query)),range(2)))
        self.assertEqual(values[0],values[1]);self.assertEqual(self.rev(),1);self.assertEqual(self.count('staff_schedule_logs'),1)
        with self.assertRaisesRegex(RuntimeError,'內容不同'):self.send('draft',{'days':[]},token=token,rev=0)
        self.send('draft_submit',{'days':fill_empty(self.month,'A',[])})
        self.assertEqual(json.loads(actor(query)),values[0])
    def test_two_tokens_stale_revision_only_one_succeeds(self):
        self.publish();queries=[self.query('draft',{'days':[day_payload(self.month,x)]},rev=0) for x in ('A','B')]
        def run(q):
            try:return actor(q)
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(run,queries))
        self.assertEqual(sum('班表已更新' in x for x in result),1);self.assertEqual(self.rev(),1)
    def test_invalid_duplicate_cross_month_seconds_and_public_off_rejected(self):
        self.publish()
        payloads=[{'days':[day_payload(self.month,'A')]*2},
            {'days':[day_payload(self.month,'A'),day_payload('2399-01-01','A')]},
            {'days':[dict(work_date=self.month,shift_code='C',start_time='10:00:01',end_time='16:00')]},
            {'days':[day_payload(self.month,'public_off')]}]
        for p in payloads:
            with self.subTest(payload=p),self.assertRaises(RuntimeError):self.send('draft',p)
            self.assertEqual(self.rev(),0)
        self.send('save',dict(work_date=self.month,shift_code='public_off'),who=ADMIN)
        with self.assertRaisesRegex(RuntimeError,'公休'):self.send('draft',{'days':[day_payload(self.month,'A')]})
    def test_other_coach_anon_direct_dml_and_private_helper_denied(self):
        self.publish()
        with self.assertRaisesRegex(RuntimeError,'自己的'):self.send('draft',{'days':[]},who=OTHER)
        with self.assertRaisesRegex(RuntimeError,'僅教練'):self.send('draft',{'days':[]},who=ADMIN)
        for q in ['delete from public.staff_schedule_days',f"select schedule_private.assert_quota('{COACH}','{self.month}')"]:
            with self.assertRaisesRegex(RuntimeError,'permission denied'):actor(q,COACH)
        with self.assertRaisesRegex(RuntimeError,'permission denied'):sql('begin;set local role anon;'+self.query('draft',{'days':[]})+';rollback;')
    def test_quota_lowered_after_preview_blocks_old_plan(self):
        d=date.fromisoformat(self.month)
        while d.weekday()>=5:d=d.replace(day=d.day+1)
        q=self.publish([{'name':'虛構假日','original_date':d.isoformat(),'observed_date':d.isoformat()}])
        values=self.values(q['total_units']//2)
        self.publish(revision=1)
        with self.assertRaisesRegex(RuntimeError,'超出'):self.send('draft',{'days':values})
        self.assertEqual(self.rev(),0)
    def test_cancelled_token_no_late_save(self):
        self.publish();token=str(uuid4());actor(f"select public.staff_schedule_operation('{token}',true)")
        with self.assertRaisesRegex(RuntimeError,'取消'):self.send('draft',{'days':[]},token=token)
    def test_fresh_upgrade_chain_in_rollback_preserves_existing_test_database(self):
        from pathlib import Path
        import re
        root=Path(__file__).resolve().parents[1]
        before=sql('select (select count(*) from public.staff_schedule_days)||\':\'||(select count(*) from public.purchases)')[0]
        tables=['staff_schedule_special_days','staff_schedule_special_months','staff_schedule_leave_logs',
            'staff_schedule_leaves','staff_schedule_allowance_logs','staff_schedule_allowances',
            'staff_schedule_logs','staff_schedule_days','staff_schedule_preferences','staff_schedule_months']
        query='begin;'+''.join('drop table public.'+name+' cascade;' for name in tables)+'drop schema schedule_private cascade;'
        # 公開SQL facade不一定有依賴追蹤；新建前清除本機交易內殘留函式。
        query+="do $x$declare p record;begin for p in select oid::regprocedure as identity from pg_proc where pronamespace='public'::regnamespace and proname like 'staff_schedule_%' loop execute 'drop function '||p.identity||' cascade';end loop;end $x$;"
        paths=['20261021083833_staff_scheduling_v1_13_22.sql','20261021091712_schedule_approved_visibility_v1_13_23.sql',
            '20261021100055_schedule_allowance_v1_13_25.sql','20261021152424_schedule_leave_v1_13_26.sql',
            '20261021160257_schedule_apply_v1_13_27.sql']
        paths.append(next(p.name for p in (root/'supabase/migrations').glob('*v1_13_29.sql')))
        paths+=['20261023114054_schedule_confirm_special_v1_13_32.sql',
            '20261023134850_schedule_manager_notes_v1_13_33.sql','20261023143211_schedule_quota_draft_v1_13_35.sql']
        for name in paths:
            if name.endswith('v1_13_32.sql'):
                query+=f"insert into public.staff_schedule_months(coach_id,month_start,coach_name,state) values('{COACH}','1980-01-01','虛構教練','approved'),('{COACH}','1980-02-01','虛構教練','draft');"
            source=(root/'supabase/migrations'/name).read_text(encoding='utf-8')
            query+=re.sub(r'(?im)^\s*(begin;|commit;)\s*$','',source)
        query+="select count(*) filter(where coach_locked)||':'||count(*) filter(where finalized_at is not null) from public.staff_schedule_months;"
        query+="select count(*) from information_schema.columns where table_schema='public' and table_name='staff_schedule_months' and column_name='coach_locked';rollback;"
        self.assertEqual(sql(query)[-2:],['1:0','1'])
        self.assertEqual(sql('select (select count(*) from public.staff_schedule_days)||\':\'||(select count(*) from public.purchases)')[0],before)
