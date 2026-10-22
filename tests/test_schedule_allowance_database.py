import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from uuid import uuid4
from test_idempotency_database import sql,actor,COACH,OTHER,ADMIN
from schedule_allowance import DEDUCT_UNITS


class AllowanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        n=int(sql('select count(*) from public.staff_schedule_allowances')[0])
        self.month=f'{2030+n//12:04d}-{n%12+1:02d}-01'
        self.payload={'holidays':[],'deduct_units':dict(DEDUCT_UNITS),'note':'虛構測試'}
    def query(self,token=None,payload=None,rev=0):
        value=json.dumps(self.payload if payload is None else payload).replace("'","''")
        return f"select public.staff_schedule_allowance_save('{token or uuid4()}','{self.month}',{rev},'{value}'::jsonb)"
    def test_reviewers_equal_coach_denied_direct_dml_and_logs(self):
        for who in (COACH,OTHER):
            with self.assertRaisesRegex(RuntimeError,'僅主管或系統管理員'):actor(self.query(),who)
        actor(self.query(),ADMIN)
        result=json.loads(actor(f"select public.staff_schedule_allowance_snapshot('{self.month}')"))
        self.assertEqual(result['record']['deduct_units']['weekend'],0)
        self.assertEqual(actor('select count(*) from public.staff_schedule_allowance_logs'), '0')
        for q in ('delete from public.staff_schedule_allowances','update public.staff_schedule_allowances set total_units=0'):
            with self.assertRaisesRegex(RuntimeError,'permission denied'):actor(q,ADMIN)
        sql(f"update public.profiles set role='manager' where id='{OTHER}'")
        try:
            query=self.query(rev=1)
            result=json.loads(actor(query,OTHER))
            self.assertEqual(result['confirmed_by'],OTHER)
            self.assertEqual(json.loads(actor(query,OTHER)),result)
            self.assertEqual(actor(f"select count(*) from public.staff_schedule_allowance_logs where month_start='{self.month}'",OTHER),'2')
            for q in ('delete from public.staff_schedule_allowances','update public.staff_schedule_allowances set total_units=0'):
                with self.assertRaisesRegex(RuntimeError,'permission denied'):actor(q,OTHER)
        finally:sql(f"update public.profiles set role='coach' where id='{OTHER}'")
    def test_same_key_concurrent_once_and_stale_revision(self):
        query=self.query()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:json.loads(actor(query,ADMIN)),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_allowance_logs where month_start='{self.month}'")[0],'1')
        with self.assertRaisesRegex(RuntimeError,'已更新'):actor(self.query(),ADMIN)
    def test_two_distinct_keys_only_one_writes(self):
        def save(_):
            try:return actor(self.query(),ADMIN)
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(save,range(2)))
        self.assertEqual(sum('額度已更新' in x for x in results),1)
    def test_bad_content_rolls_back_and_cancel_blocks_late_send(self):
        before=sql('select count(*) from public.staff_schedule_allowances')[0]
        bad=dict(self.payload,deduct_units=dict(DEDUCT_UNITS,weekend=2))
        with self.assertRaisesRegex(RuntimeError,'已確認規則'):actor(self.query(payload=bad),ADMIN)
        self.assertEqual(sql('select count(*) from public.staff_schedule_allowances')[0],before)
        token=str(uuid4());actor(f"select public.staff_schedule_operation('{token}',true)",ADMIN)
        with self.assertRaisesRegex(RuntimeError,'取消'):actor(self.query(token),ADMIN)
    def test_overlap_duplicate_and_cross_month(self):
        self.month='2026-10-01'
        holidays=[{'name':'虛構假日','original_date':'2026-10-10','observed_date':'2026-10-12'}]
        old_revision=int(sql("select coalesce((select revision from public.staff_schedule_allowances where month_start='2026-10-01'),0)")[0])
        result=json.loads(actor(self.query(payload=dict(self.payload,holidays=holidays),rev=old_revision),ADMIN))
        self.assertEqual((result['saturday_days'],result['holiday_days'],result['total_units']),(5,1,12))
        with self.assertRaisesRegex(RuntimeError,'重複'):actor(self.query(payload=dict(self.payload,holidays=holidays*2),rev=old_revision+1),ADMIN)
        self.month='2026-02-01'
        rows=[{'name':'虛構跨月假日','original_date':'2026-01-31','observed_date':'2026-02-02'}]
        old_revision=int(sql("select coalesce((select revision from public.staff_schedule_allowances where month_start='2026-02-01'),0)")[0])
        result=json.loads(actor(self.query(payload=dict(self.payload,holidays=rows),rev=old_revision),ADMIN))
        self.assertEqual(result['total_units'],10)
    def test_cross_month_concurrent_cannot_count_same_holiday_twice(self):
        from datetime import date,timedelta
        year=2100+int(sql('select count(*) from public.staff_schedule_allowances')[0])
        original=next(date(year,10,n) for n in range(1,8) if date(year,10,n).weekday()==5)
        def save(month):
            self_month=f'{year}-{month:02d}-01'
            observed=(original+timedelta(days=2)) if month==10 else next(date(year,11,n) for n in range(1,8) if date(year,11,n).weekday()==0)
            payload=dict(self.payload,holidays=[{'name':'虛構競爭補假','original_date':original.isoformat(),'observed_date':observed.isoformat()}])
            encoded=json.dumps(payload).replace("'","''")
            query=f"select public.staff_schedule_allowance_save('{uuid4()}','{self_month}',0,'{encoded}'::jsonb)"
            try:return actor(query,ADMIN)
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(save,(10,11)))
        self.assertEqual(sum('其他月份' in x for x in results),1)
    def test_inactive_and_anon_denied(self):
        sql(f"update public.profiles set active=false where id='{COACH}'")
        try:
            with self.assertRaisesRegex(RuntimeError,'權限|停用'):actor(f"select public.staff_schedule_allowance_snapshot('{self.month}')")
        finally:sql(f"update public.profiles set active=true where id='{COACH}'")
        with self.assertRaisesRegex(RuntimeError,'permission denied'):
            sql(f"begin;set local role anon;select public.staff_schedule_allowance_snapshot('{self.month}');rollback;")
    def test_fresh_install_rollback_and_service_backup_read(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'supabase/migrations/20261021100055_schedule_allowance_v1_13_25.sql').read_text(encoding='utf-8')
        query="begin;drop function public.staff_schedule_allowance_save(uuid,date,integer,jsonb),public.staff_schedule_allowance_snapshot(date);"
        query+="drop function schedule_private.allowance_save(uuid,date,integer,jsonb);drop table public.staff_schedule_allowance_logs,public.staff_schedule_allowances;"
        before=sql('select count(*) from public.purchases')[0]
        self.assertEqual(sql(query+source+'select count(*) from public.staff_schedule_allowances;rollback;')[-1],'0')
        self.assertEqual(sql('select count(*) from public.purchases')[0],before)
        self.assertTrue(sql('begin;set local role service_role;select count(*) from public.staff_schedule_allowances;rollback;'))
