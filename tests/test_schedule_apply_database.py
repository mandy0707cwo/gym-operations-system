import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from uuid import uuid4
from test_idempotency_database import sql,actor,COACH,OTHER,ADMIN


class ApplyDatabaseTests(unittest.TestCase):
    def setUp(self):
        n=int(sql("select count(*) from public.staff_schedule_months where month_start>=date '2400-01-01'")[0])
        self.month=f'{2400+n//12:04d}-{n%12+1:02d}-01'
    def query(self,token=None,base='B',rev=0,coach=COACH,reason=''):
        payload=json.dumps({'base_shift':base,'reason':reason}).replace("'","''")
        return f"select public.staff_schedule_command('{token or uuid4()}','{coach}','{self.month}',{rev},'apply','{payload}'::jsonb)"
    def test_first_apply_atomic_replay_once_and_sunday_default(self):
        query=self.query()
        with ThreadPoolExecutor(2) as pool:replies=list(pool.map(lambda _:json.loads(actor(query)),range(2)))
        self.assertEqual(replies[0],replies[1]);self.assertEqual(replies[0]['revision'],1)
        self.assertEqual(sql(f"select base_shift from public.staff_schedule_preferences where coach_id='{COACH}'")[0],'B')
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_logs where coach_id='{COACH}' and month_start='{self.month}'")[0],'1')
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_days where coach_id='{COACH}' and month_start='{self.month}' and extract(isodow from work_date)=7 and shift_code<>'regular_off'")[0],'0')
    def test_fill_failure_rolls_back_base_month_days_log_and_receipt(self):
        before=sql(f"select base_shift from public.staff_schedule_preferences where coach_id='{COACH}'")
        token=str(uuid4())
        sql("create function public.test_apply_failure() returns trigger language plpgsql as $$ begin raise exception '虛構日寫入失敗';end $$;create trigger test_apply_failure before insert on public.staff_schedule_days for each row execute function public.test_apply_failure();")
        try:
            with self.assertRaisesRegex(RuntimeError,'日寫入失敗'):actor(self.query(token,base='A'))
        finally:sql('drop trigger test_apply_failure on public.staff_schedule_days;drop function public.test_apply_failure();')
        self.assertEqual(sql(f"select base_shift from public.staff_schedule_preferences where coach_id='{COACH}'"),before)
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_months where month_start='{self.month}'")[0],'0')
        self.assertEqual(json.loads(actor(f"select public.staff_schedule_operation('{token}')"))['state'],'not_found')
    def test_two_keys_stale_only_one_succeeds_and_cancel(self):
        def apply(base):
            try:return actor(self.query(base=base))
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:replies=list(pool.map(apply,('A','B')))
        self.assertEqual(sum('已更新' in x for x in replies),1)
        token=str(uuid4());actor(f"select public.staff_schedule_operation('{token}',true)")
        with self.assertRaisesRegex(RuntimeError,'取消'):actor(self.query(token,rev=1))
    def test_preserve_manual_day_and_require_manager_reason(self):
        payload=json.dumps({'work_date':self.month,'shift_code':'full_off'})
        actor(f"select public.staff_schedule_command('{uuid4()}','{COACH}','{self.month}',0,'save','{payload}'::jsonb)")
        actor(self.query(rev=1))
        self.assertEqual(sql(f"select shift_code from public.staff_schedule_days where coach_id='{COACH}' and work_date='{self.month}'")[0],'full_off')
        with self.assertRaisesRegex(RuntimeError,'須填寫原因'):actor(self.query(rev=2),ADMIN)
        actor(self.query(rev=2,reason='虛構代填'),ADMIN)
        with self.assertRaisesRegex(RuntimeError,'自己'):actor(self.query(coach=OTHER))
    def test_submit_locked_invalid_base_and_inactive_no_write(self):
        with self.assertRaisesRegex(RuntimeError,'選擇A班或B班'):actor(self.query(base='C'))
        actor(self.query())
        actor(f"select public.staff_schedule_command('{uuid4()}','{COACH}','{self.month}',1,'submit','{{}}'::jsonb)")
        with self.assertRaisesRegex(RuntimeError,'不可修改'):actor(self.query(rev=2))
        sql(f"update public.profiles set active=false where id='{OTHER}'")
        try:
            with self.assertRaisesRegex(RuntimeError,'權限|停用'):actor(self.query(coach=OTHER),OTHER)
        finally:sql(f"update public.profiles set active=true where id='{OTHER}'")
