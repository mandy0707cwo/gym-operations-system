"""工作區獨立 PostgreSQL 的真實雙連線測試，所有身分及交易皆虛構。"""
import json
from pathlib import Path
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import time
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
PSQL = WORKSPACE / "tools/postgres_idempotency_test/pgsql/bin/psql.exe"
ADMIN = "00000000-0000-4000-8000-000000000001"
COACH = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
MEMBER = "00000000-0000-4000-8000-000000000004"
CATALOG = "00000000-0000-4000-8000-000000000005"


def sql(query):
    env = dict(os.environ, PGCLIENTENCODING="UTF8")
    for key in ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGOPTIONS"):
        env.pop(key, None)
    result = subprocess.run([str(PSQL), "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
        "-h", "127.0.0.1", "-p", "55439", "-U", "postgres", "-d", "postgres"],
        input=query, text=True, encoding="utf-8", capture_output=True, env=env, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line.strip()]


def actor(query, who=COACH):
    return sql("BEGIN; SELECT set_config('request.jwt.claim.sub','" + who + "',true);"
        " SELECT set_config('request.jwt.claim.role','authenticated',true); SET LOCAL ROLE authenticated; "
        + query + "; COMMIT;")[-1]


def purchase(token=None, total=2100, paid=2100, coach=COACH):
    token = token or str(uuid4())
    payload = {"member_id": MEMBER, "coach_id": coach, "course_name": "隔離測試課程", "report_category": "測試",
        "purchase_kind": "first", "payment_plan": "full", "installment_count": 1,
        "total_sessions": 3, "session_hours": 1, "total_amount": total,
        "purchase_date": "2099-01-01", "expiry_date": "2099-12-31"}
    first = {"amount": paid, "paid_date": "2099-01-01"}
    query = "SELECT public.create_purchase_idempotent('" + token + "','" + json.dumps(payload) + "'::jsonb,'" + json.dumps(first) + "'::jsonb)"
    return token, query


class DatabaseIdempotencyTests(unittest.TestCase):
    def test_01_same_purchase_double_connection(self):
        token, request = purchase()
        count_before = int(sql("select count(*) from public.purchases")[0])
        with ThreadPoolExecutor(2) as pool:
            replies = list(pool.map(lambda _: json.loads(actor(request)), range(2)))
        self.assertEqual(replies[0], replies[1])
        self.assertEqual(int(sql("select count(*) from public.purchases")[0]), count_before + 1)
        pid = replies[0]["id"]
        self.assertEqual(int(sql(f"select count(*) from public.purchase_payments where purchase_id='{pid}'")[0]), 1)
        changed = purchase(token, total=2200, paid=2200)[1]
        with self.assertRaisesRegex(RuntimeError, "內容不同"):
            actor(changed)

    def test_02_usage_concurrency_and_completed_last_replay(self):
        pid = json.loads(actor(purchase()[1]))["id"]
        for seq in range(1, 4):
            token = str(uuid4())
            query = f"select public.consume_session_idempotent('{token}','{pid}','2099-01-0{seq+1}','{COACH}')"
            with ThreadPoolExecutor(2) as pool:
                replies = list(pool.map(lambda _: json.loads(actor(query)), range(2)))
            self.assertEqual(replies[0], replies[1])
            self.assertEqual(replies[0]["session_seq"], seq)
            self.assertEqual(int(sql(f"select count(*) from public.session_usages where purchase_id='{pid}'")[0]), seq)
        self.assertEqual(sql(f"select status from public.purchases where id='{pid}'")[0], "completed")
        self.assertEqual(json.loads(actor(query)), replies[0])
        self.assertEqual(sql(f"select sum(deducted_net_amount) from public.session_usages where purchase_id='{pid}'")[0], "2000.00")

    def test_03_failed_first_payment_leaves_neither_transaction_nor_receipt(self):
        before = sql("select count(*)||':'||(select count(*) from public.purchase_payments) from public.purchases")[0]
        token, query = purchase(paid=2200)
        with self.assertRaises(RuntimeError):
            actor(query)
        self.assertEqual(sql("select count(*)||':'||(select count(*) from public.purchase_payments) from public.purchases")[0], before)
        state = json.loads(actor(f"select public.operation_status('{token}','purchase')"))
        self.assertEqual(state["state"], "not_found")
        # 真正測試購課 INSERT 後、首款 INSERT 時失敗，不只測試輸入前置驗證。
        sql("create function public.test_reject_first_payment() returns trigger language plpgsql as $$ begin if new.amount=4210 then raise exception '測試首款寫入失敗'; end if; return new; end $$; create trigger test_reject_first_payment before insert on public.purchase_payments for each row execute function public.test_reject_first_payment();")
        try:
            key2, query2 = purchase(total=4210, paid=4210)
            with self.assertRaisesRegex(RuntimeError, "首款寫入失敗"):
                actor(query2)
            self.assertEqual(sql("select count(*)||':'||(select count(*) from public.purchase_payments) from public.purchases")[0], before)
            self.assertEqual(json.loads(actor(f"select public.operation_status('{key2}','purchase')"))["state"],"not_found")
        finally:
            sql("drop trigger test_reject_first_payment on public.purchase_payments; drop function public.test_reject_first_payment();")

    def test_04_cancel_blocks_late_request(self):
        token, query = purchase()
        result = json.loads(actor(f"select public.cancel_operation('{token}','purchase')"))
        self.assertEqual(result["state"], "cancelled")
        with self.assertRaisesRegex(RuntimeError, "已取消"):
            actor(query)

    def test_05_success_reply_survives_status_cancel_and_changed_role(self):
        token, query = purchase()
        result = json.loads(actor(query))
        for method in ("operation_status", "cancel_operation"):
            receipt = json.loads(actor(f"select public.{method}('{token}','purchase')"))
            self.assertEqual(receipt["state"], "completed")
            self.assertEqual(receipt["result"], result)
        # 不同使用者不知道原結果；相同 UUID 在另一人名下不會讀到此收據。
        other = json.loads(actor(f"select public.operation_status('{token}','purchase')", OTHER))
        self.assertEqual(other["state"], "not_found")

    def test_06_unauthorized_and_inactive(self):
        _, query = purchase(coach=OTHER)
        with self.assertRaisesRegex(RuntimeError, "教練僅可"):
            actor(query)
        pid = json.loads(actor(purchase(coach=OTHER)[1], ADMIN))["id"]
        with self.assertRaisesRegex(RuntimeError, "無權"):
            actor(f"select public.consume_session_idempotent('{uuid4()}','{pid}','2099-01-02','{COACH}')")
        sql(f"update public.profiles set active=false where id='{COACH}'")
        try:
            with self.assertRaisesRegex(RuntimeError, "停用"):
                actor(purchase()[1])
        finally:
            sql(f"update public.profiles set active=true where id='{COACH}'")

    def test_07_makeup_and_direct_receipt_access_denied(self):
        pid = json.loads(actor(purchase()[1]))["id"]
        with self.assertRaisesRegex(RuntimeError, "系統管理員"):
            actor(f"select public.consume_session_idempotent('{uuid4()}','{pid}','2099-01-02','{COACH}',null,true,'2099-01-01')")
        for query in ("select * from operation_private.requests", "delete from operation_private.requests"):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                actor(query)
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            sql(f"begin; set local role anon; select public.operation_status('{uuid4()}','usage'); rollback;")

    def test_08_key_cannot_switch_kind_and_new_key_is_new_operation(self):
        token, query = purchase()
        result = json.loads(actor(query))
        with self.assertRaisesRegex(RuntimeError, "操作類型"):
            actor(f"select public.operation_status('{token}','usage')")
        another = json.loads(actor(purchase()[1]))
        self.assertNotEqual(result["id"], another["id"])

    def test_09_waiting_concurrent_request_replays_after_commit(self):
        token, query = purchase()
        # 首連線在建立收據後延遲提交；第二連線必須等待，再取首筆結果。
        first = "BEGIN; SELECT set_config('request.jwt.claim.sub','" + COACH + "',true); SET LOCAL ROLE authenticated; " + query + "; select pg_sleep(1); COMMIT;"
        with ThreadPoolExecutor(2) as pool:
            future = pool.submit(sql, first)
            time.sleep(.2)
            started=time.monotonic()
            second = json.loads(actor(query))
            waited=time.monotonic()-started
            lines = future.result()
        initial = next(json.loads(line) for line in lines if line.startswith('{'))
        self.assertEqual(initial, second)
        self.assertGreater(waited,.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
