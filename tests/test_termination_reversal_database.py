"""僅對固定本機假資料庫測試；不連正式服務、不使用正式會員。"""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from termination_db import sql,actor,course,reverse,ADMIN,COACH,OTHER


class ReversalDatabaseTests(unittest.TestCase):
    def test_migration_preserves_historical_row(self):
        self.assertEqual(sql("select (to_jsonb(t)-'reversed_at')=b.original from public.course_terminations t join public.test_v37_baseline b using(id)")[0],'t')

    def test_expired_and_refund_restore_without_changing_money_or_expiry(self):
        for kind in ('expired','refund'):
            pid,tid=course(kind);before=sql(f"select (to_jsonb(t)-'reversed_at')::text from public.course_terminations t where id='{tid}'")[0]
            money=sql(f"select sum(amount)||':'||sum(net_amount) from public.purchase_payments where purchase_id='{pid}'")[0]
            response=json.loads(actor(reverse(tid)))
            self.assertEqual(response['restored_status'],'active')
            self.assertEqual(sql(f"select status||':'||expiry_date from public.purchases where id='{pid}'")[0],'active:2099-12-31')
            self.assertEqual(sql(f"select (to_jsonb(t)-'reversed_at')::text from public.course_terminations t where id='{tid}'")[0],before)
            self.assertEqual(sql(f"select sum(amount)||':'||sum(net_amount) from public.purchase_payments where purchase_id='{pid}'")[0],money)
            self.assertEqual(sql(f"select count(*) from public.session_usages where purchase_id='{pid}'")[0],'0')
            self.assertEqual(sql(f"select sum(remaining_amount)||':'||sum(remaining_net_amount)||':'||sum(refund_net_amount) from public.course_termination_events where purchase_id='{pid}'")[0],'0.00:0:0')

    def test_same_key_concurrent_one_row_same_result_and_changed_payload_rejected(self):
        pid,tid=course();key=str(uuid4());query=reverse(tid,key)
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda _:json.loads(actor(query)),range(2)))
        self.assertEqual(result[0],result[1])
        self.assertEqual(sql(f"select count(*) from public.course_termination_reversals where termination_id='{tid}'")[0],'1')
        with self.assertRaisesRegex(RuntimeError,'內容不同'):actor(reverse(tid,key,reason='不同內容'))

    def test_different_keys_do_not_reverse_twice(self):
        pid,tid=course()
        def send(_):
            try:return json.loads(actor(reverse(tid)))
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(send,range(2)))
        self.assertEqual(sum(isinstance(x,dict) for x in result),1)
        self.assertTrue(any('已撤銷' in x for x in result if isinstance(x,str)))

    def test_role_active_ack_and_reason_gates(self):
        pid,tid=course()
        for who in (COACH,OTHER):
            with self.assertRaisesRegex(RuntimeError,'系統管理員'):actor(reverse(tid),who)
        for role in ('manager','shared_coach'):
            with self.assertRaisesRegex(RuntimeError,'系統管理員'):
                sql(f"begin;update public.profiles set role='{role}' where id='{ADMIN}';select set_config('request.jwt.claim.sub','{ADMIN}',true);set local role authenticated;{reverse(tid)};rollback;")
        with self.assertRaisesRegex(RuntimeError,'系統管理員'):
            sql(f"begin;update public.profiles set active=false where id='{ADMIN}';select set_config('request.jwt.claim.sub','{ADMIN}',true);set local role authenticated;{reverse(tid)};rollback;")
        with self.assertRaisesRegex(RuntimeError,'確認'):actor(reverse(tid,ack=False))
        with self.assertRaisesRegex(RuntimeError,'原因'):actor(reverse(tid,reason=' '))
        self.assertEqual(sql(f"select count(*) from public.course_termination_reversals where termination_id='{tid}'")[0],'0')

    def test_reversed_original_frozen_and_new_usage_does_not_rebuild_it(self):
        pid,tid=course();actor(reverse(tid))
        before=sql(f"select to_jsonb(t)::text from public.course_terminations t where id='{tid}'")[0]
        actor(f"select public.consume_session_idempotent('{uuid4()}','{pid}',(now() at time zone 'Asia/Taipei')::date,'{COACH}')")
        self.assertEqual(sql(f"select to_jsonb(t)::text from public.course_terminations t where id='{tid}'")[0],before)
        with self.assertRaisesRegex(RuntimeError,'不可修改'):sql(f"update public.course_terminations set reason='改寫' where id='{tid}'")
        with self.assertRaisesRegex(RuntimeError,'不可刪除'):sql(f"delete from public.course_terminations where id='{tid}'")

    def test_reterminate_and_old_success_replay_does_not_undo_new_cycle(self):
        pid,tid=course();query=reverse(tid);first=json.loads(actor(query))
        actor(f"select public.terminate_course('{pid}',(now() at time zone 'Asia/Taipei')::date,'expired',false,false,null,'再次虛構中止',null)")
        self.assertEqual(json.loads(actor(query)),first)
        self.assertEqual(sql(f"select status from public.purchases where id='{pid}'")[0],'expired')
        self.assertEqual(sql(f"select count(*) from public.course_terminations where purchase_id='{pid}'")[0],'2')
        self.assertEqual(sql(f"select count(*) from public.course_terminations where purchase_id='{pid}' and reversed_at is null")[0],'1')

    def test_historical_events_and_no_backdated_service_in_inactive_interval(self):
        pid,tid=course('refund');actor(reverse(tid))
        self.assertEqual(sql(f"select count(*) from public.course_termination_events where purchase_id='{pid}' and termination_date='2026-01-31'")[0],'1')
        self.assertEqual(sql(f"select sum(remaining_net_amount) from public.course_termination_events where purchase_id='{pid}' and termination_date='2026-01-31'")[0],'2000')
        with self.assertRaisesRegex(RuntimeError,'有效中止期間'):
            actor(f"select public.consume_session_idempotent('{uuid4()}','{pid}','2026-02-01','{COACH}')")

    def test_direct_dml_anon_and_original_fake_flags_denied(self):
        pid,tid=course()
        with self.assertRaisesRegex(RuntimeError,'permission denied'):sql('set role anon;'+reverse(tid))
        with self.assertRaisesRegex(RuntimeError,'permission denied'):actor('delete from public.course_termination_reversals')
        with self.assertRaisesRegex(RuntimeError,'permission denied'):actor("insert into public.course_termination_reversals(id) values(gen_random_uuid())")
        with self.assertRaisesRegex(RuntimeError,'完整撤銷'):sql(f"update public.course_terminations set reversed_at=now() where id='{tid}'")
        self.assertEqual(actor('select count(*) from public.course_termination_events',COACH),'0')

    def test_reversal_records_are_immutable(self):
        pid,tid=course();actor(reverse(tid))
        for action in (f"update public.course_termination_reversals set reason='改寫' where termination_id='{tid}'",f"delete from public.course_termination_reversals where termination_id='{tid}'"):
            with self.assertRaisesRegex(RuntimeError,'不可修改或刪除'):sql(action)

    def test_future_termination_and_status_mismatch_stop(self):
        pid,tid=course();sql(f"update public.course_terminations set termination_date='2099-01-31' where id='{tid}'")
        with self.assertRaisesRegex(RuntimeError,'晚於今日'):actor(reverse(tid))
        pid,tid=course();sql(f"update public.purchases set status='active' where id='{pid}'")
        with self.assertRaisesRegex(RuntimeError,'狀態與原中止不符'):actor(reverse(tid))

    def test_partial_failure_rolls_back_reversal_marker_and_purchase(self):
        pid,tid=course();name='test_reverse_failure_'+uuid4().hex
        sql(f"create function public.{name}() returns trigger language plpgsql as $$begin if new.id='{pid}' and new.status='active' then raise exception '虛構儲存拒絕';end if;return new;end $$;create trigger {name} before update on public.purchases for each row execute function public.{name}();")
        try:
            with self.assertRaisesRegex(RuntimeError,'虛構儲存拒絕'):actor(reverse(tid))
            self.assertEqual(sql(f"select count(*) from public.course_termination_reversals where termination_id='{tid}'")[0],'0')
            self.assertEqual(sql(f"select reversed_at is null from public.course_terminations where id='{tid}'")[0],'t')
            self.assertEqual(sql(f"select status from public.purchases where id='{pid}'")[0],'expired')
        finally:sql(f'drop trigger {name} on public.purchases;drop function public.{name}();')
