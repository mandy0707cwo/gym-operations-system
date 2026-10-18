"""操作識別碼的純測試；不使用正式資料庫或機密。"""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from operation_requests import Operation


class FakeDB:
    def __init__(self):
        self.receipts = {}
        self.writes = 0
        self.lose_reply = False
        self.reject = False
        self.last_token = None

    def rpc(self, name, payload):
        def execute():
            token = payload["p_operation_id"]
            self.last_token = token
            if name == "operation_status":
                return SimpleNamespace(data=deepcopy(self.receipts.get(token, {"state": "not_found"})))
            if name == "cancel_operation":
                self.receipts.setdefault(token, {"state": "cancelled"})
                return SimpleNamespace(data=deepcopy(self.receipts[token]))
            if self.reject:
                raise RuntimeError("交易拒絕")
            row = self.receipts.get(token)
            if row and row["state"] == "cancelled":
                raise ValueError("已取消")
            if row:
                if row["request"] != payload:
                    raise ValueError("同碼不同內容")
                return SimpleNamespace(data=deepcopy(row["result"]))
            self.writes += 1
            result = {"id": "p" + str(self.writes), "purchase_id": "p" + str(self.writes), "payment_id": "pay" + str(self.writes)}
            self.receipts[token] = {"state": "completed", "result": result, "request": deepcopy(payload)}
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError("回覆遺失，但資料庫已成功")
            return SimpleNamespace(data=deepcopy(result))
        return SimpleNamespace(execute=execute)


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.st = SimpleNamespace(session_state={}, query_params={})
        self.db = FakeDB()
        self.me = {"id": "coach", "role": "coach"}
        self.payload = {"p_purchase": {"total_amount": 2100}, "p_first_payment": {"amount": 2100}}

    def op(self, kind="purchase"):
        return Operation(self.st, lambda: self.db, self.me, kind)

    def test_token_stable_rerun_and_url_refresh(self):
        first = self.op().data["id"]
        self.assertEqual(first, self.op().data["id"])
        self.st.session_state.clear()
        self.assertEqual(first, self.op().data["id"])

    def test_repeated_same_payload_returns_original(self):
        operation = self.op()
        first = operation.submit(self.payload).data
        second = operation.submit(deepcopy(self.payload)).data
        self.assertEqual(first, second)
        self.assertEqual(self.db.writes, 1)

    def test_lost_reply_retry_only_one_write(self):
        operation = self.op()
        self.db.lose_reply = True
        with self.assertRaises(TimeoutError):
            operation.submit(self.payload)
        self.assertEqual(operation.data["state"], "uncertain")
        original = operation.data["id"]
        operation.submit(self.payload)
        self.assertEqual(operation.data["id"], original)
        self.assertEqual(self.db.writes, 1)

    def test_refresh_after_unknown_recovers_completed(self):
        self.db.lose_reply = True
        with self.assertRaises(TimeoutError):
            self.op().submit(self.payload)
        self.st.session_state.clear()
        recovered = self.op()
        self.assertEqual(recovered.data["state"], "completed")
        self.assertEqual(self.db.writes, 1)

    def test_same_code_changed_content_rejected(self):
        operation = self.op()
        operation.submit(self.payload)
        other = deepcopy(self.payload)
        other["p_first_payment"]["amount"] = 100
        with self.assertRaises(ValueError):
            operation.submit(other)
        self.assertEqual(self.db.writes, 1)

    def test_next_requires_resolved_and_changes_code(self):
        operation = self.op()
        original = operation.data["id"]
        with self.assertRaises(ValueError):
            operation.next()
        operation.submit(self.payload)
        operation.next()
        next_operation = self.op()
        self.assertNotEqual(original, next_operation.data["id"])
        next_operation.submit(self.payload)
        self.assertEqual(self.db.writes, 2)

    def test_cancel_rejected_operation_and_delayed_call(self):
        operation = self.op()
        self.db.reject = True
        with self.assertRaises(RuntimeError):
            operation.submit(self.payload)
        self.db.reject = False
        operation.cancel()
        self.assertEqual(operation.data["state"], "cancelled")
        with self.assertRaises(ValueError):
            operation.submit(self.payload)
        self.assertEqual(self.db.writes, 0)

    def test_cancel_after_success_returns_success_not_delete(self):
        operation = self.op()
        self.db.lose_reply = True
        with self.assertRaises(TimeoutError):
            operation.submit(self.payload)
        operation.cancel()
        self.assertEqual(operation.data["state"], "completed")
        self.assertEqual(self.db.writes, 1)

    def test_purchase_usage_namespaces_and_no_payload_in_url(self):
        self.assertNotEqual(self.op().data["id"], self.op("usage").data["id"])
        self.assertEqual(set(self.st.query_params), {"op_purchase", "op_usage"})
        self.assertNotIn("2100", str(self.st.query_params))

    def test_invalid_url_token_replaced(self):
        self.st.query_params["op_purchase"] = "malformed"
        self.assertNotEqual(self.op().data["id"], "malformed")

    def test_cross_actor_clears_local_payload(self):
        operation = self.op()
        self.db.reject = True
        with self.assertRaises(RuntimeError):
            operation.submit(self.payload)
        self.me = {"id": "other", "role": "coach"}
        # 真實資料庫還會依 actor 隔離收據；此處驗證 session 不沿用另一人的 payload。
        self.assertIsNone(self.op().data["payload"])


if __name__ == "__main__":
    unittest.main()
