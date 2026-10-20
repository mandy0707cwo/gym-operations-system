"""僅使用本機虛構 PostgreSQL；拒絕時銷課、日營運與操作收據全部不新增。"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from uuid import uuid4
from test_idempotency_database import sql,actor,purchase,COACH,ADMIN,OTHER


class UsageFundsDatabaseTests(unittest.TestCase):
    def make(self,paid=700,total=2100):
        query=purchase(total=total,paid=paid)[1]
        if paid<total:
            query=query.replace('"payment_plan": "full"','"payment_plan": "installment"').replace('"installment_count": 1','"installment_count": 3')
        return json.loads(actor(query))['id']

    def request(self,pid,token=None,who=COACH):
        return f"select public.consume_session_idempotent('{token or uuid4()}','{pid}','2099-01-02','{who}')"

    def test_short_rejected_atomic_and_can_retry_same_key_after_payment(self):
        pid=self.make(paid=699.99)
        key=str(uuid4());query=self.request(pid,key)
        before=sql('select count(*) from public.daily_operations')[0]
        with self.assertRaisesRegex(RuntimeError,'實際預收餘額不足'): actor(query)
        self.assertEqual(sql(f"select count(*) from public.session_usages where purchase_id='{pid}'")[0],'0')
        self.assertEqual(sql(f"select count(*) from operation_private.requests where operation_id='{key}'")[0],'0')
        self.assertEqual(sql('select count(*) from public.daily_operations')[0],before)
        sql(f"update public.purchase_payments set amount=700 where purchase_id='{pid}'")
        self.assertEqual(json.loads(actor(query))['session_seq'],1)
        self.assertEqual(json.loads(actor(query))['session_seq'],1)

    def test_second_new_key_cannot_spend_same_receipt(self):
        pid=self.make()
        actor(self.request(pid))
        with self.assertRaisesRegex(RuntimeError,'實際預收餘額不足'): actor(self.request(pid))

    def test_different_key_two_connections_only_one_succeeds(self):
        pid=self.make()
        def send(_):
            try: return actor(self.request(pid))
            except RuntimeError as exc: return str(exc)
        with ThreadPoolExecutor(2) as pool: replies=list(pool.map(send,range(2)))
        self.assertEqual(sum('實際預收餘額不足' in r for r in replies),1)
        self.assertEqual(sql(f"select count(*) from public.session_usages where purchase_id='{pid}'")[0],'1')

    def test_direct_insert_cannot_bypass_balance_or_undercharge(self):
        pid=self.make(paid=1)
        for amount,message in [(700,'實際預收餘額不足'),(1,'分攤規則')]:
            q=f"insert into public.session_usages(purchase_id,usage_date,actual_usage_date,coach_id,session_seq,deducted_amount,deducted_net_amount,created_by) values ('{pid}','2099-01-02','2099-01-02','{COACH}',1,{amount},1,'{COACH}')"
            with self.assertRaisesRegex(RuntimeError,message): actor(q)

    def test_existing_admin_and_manager_permissions_unchanged(self):
        for role in ('admin','manager','shared_coach'):
            pid=self.make(paid=1)
            sql(f"update public.profiles set role='{role}' where id='{ADMIN}'")
            try:
                actor(self.request(pid),ADMIN)
                self.assertEqual(sql(f"select count(*) from public.session_usages where purchase_id='{pid}'")[0],'1')
            finally: sql(f"update public.profiles set role='admin' where id='{ADMIN}'")

    def test_last_cent_remainder_and_net_total_unchanged(self):
        pid=self.make(paid=100,total=100)
        amounts=[json.loads(actor(self.request(pid)))['deducted_amount'] for _ in range(3)]
        self.assertEqual(amounts,[33.33,33.33,33.34])
        self.assertEqual(sql(f"select sum(deducted_net_amount) from public.session_usages where purchase_id='{pid}'")[0],'95.00')

    def test_last_session_one_cent_short_is_not_discounted(self):
        pid=self.make(paid=99.99,total=100)
        actor(self.request(pid));actor(self.request(pid))
        key=str(uuid4());query=self.request(pid,key)
        with self.assertRaisesRegex(RuntimeError,'實際預收餘額不足'): actor(query)
        self.assertEqual(sql(f"select status from public.purchases where id='{pid}'")[0],'active')
        sql(f"update public.purchase_payments set amount=100 where purchase_id='{pid}'")
        self.assertEqual(json.loads(actor(query))['deducted_amount'],33.34)

    def test_usage_by_another_execution_coach_is_also_deducted(self):
        pid=self.make(paid=700)
        actor(self.request(pid,who=OTHER),ADMIN)
        with self.assertRaisesRegex(RuntimeError,'實際預收餘額不足'):actor(self.request(pid))

    def test_inactive_cannot_direct_insert(self):
        pid=self.make()
        sql(f"update public.profiles set active=false where id='{COACH}'")
        try:
            q=f"insert into public.session_usages(purchase_id,usage_date,actual_usage_date,coach_id,session_seq,deducted_amount,deducted_net_amount,created_by) values ('{pid}','2099-01-02','2099-01-02','{COACH}',1,700,667,'{COACH}')"
            with self.assertRaisesRegex(RuntimeError,'停用'): actor(q)
        finally: sql(f"update public.profiles set active=true where id='{COACH}'")

    def test_trigger_not_callable_api_and_migration_no_history_writes(self):
        with self.assertRaisesRegex(RuntimeError,'permission denied'):
            actor('select finance_private.enforce_usage_funds_v1()')
        source=(Path(__file__).resolve().parents[1]/'supabase/migrations/20261020023026_usage_funds_guard_v1_13_21.sql').read_text(encoding='utf-8')
        self.assertNotIn('update public.',source.lower())
        self.assertNotIn('delete from',source.lower())
