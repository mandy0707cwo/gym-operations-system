"""購課與銷課操作識別碼：URL 只保存隨機碼，內容及結果留在伺服器／私有資料庫。"""
from copy import deepcopy
from datetime import datetime
import json
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo


def response_object(response):
    data = getattr(response, "data", None)
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("尚未取得完整操作確認，請保留原識別碼查核或重試。")
    return data


def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Operation:
    """一筆操作直到明確完成或取消前不換碼；不可用日期、金額猜重複。"""
    def __init__(self, st, client, me, kind):
        if kind not in ("purchase", "usage"):
            raise ValueError("無效操作種類")
        self.st, self.client, self.me, self.kind = st, client, me, kind
        self.query_key = "op_" + kind
        self.state_key = "_operation_" + kind
        raw = st.query_params.get(self.query_key)
        try:
            token = str(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            token = str(uuid4())
            st.query_params[self.query_key] = token
            raw = None
        previous = st.session_state.get(self.state_key)
        if not previous or previous.get("actor") != str(me["id"]) or previous.get("id") != token:
            previous = {"actor": str(me["id"]), "id": token, "state": "new", "payload": None, "result": None}
            st.session_state[self.state_key] = previous
            self.data = previous
            if raw is not None:
                # 重新整理可能遺失 Session State，先向資料庫查原操作，不因空表單換碼。
                self.data["state"] = "uncertain"
                try:
                    self.resolve()
                except Exception as exc:
                    self.data["error"] = str(exc)
        else:
            self.data = previous

    def resolve(self):
        status = response_object(self.client().rpc("operation_status", {
            "p_operation_id": self.data["id"], "p_kind": self.kind}).execute())
        state = status.get("state")
        if state not in ("completed", "cancelled", "not_found"):
            raise ValueError("操作查核回覆不完整；不允許自動換新識別碼。")
        if state == "completed":
            self._completed(status.get("result"))
        elif state == "cancelled":
            self.data["state"] = "cancelled"
        else:
            # not_found 不能證明稍後抵達的舊請求不會成功；只能原碼重試或先保存取消墓碑。
            self.data["state"] = "new" if self.data.get("payload") is None else "uncertain"
        return status

    def _completed(self, result):
        if not isinstance(result, dict) or not result.get("id"):
            raise ValueError("成功回覆缺少交易識別碼，請查核原操作。")
        if self.kind == "purchase" and (not result.get("payment_id") or result.get("purchase_id") != result["id"]):
            raise ValueError("購課與首期付款確認不完整，請查核原操作。")
        if self.kind == "usage" and (not result.get("purchase_id") or (self.data.get("payload") is not None
                and result["purchase_id"] != self.data["payload"].get("p_purchase_id"))):
            raise ValueError("銷課確認與原購課不符，請查核原操作。")
        self.data.update(state="completed", result=deepcopy(result))
        if self.kind == "purchase":
            today = datetime.now(ZoneInfo("Asia/Taipei")).date()
            self.st.session_state["_purchase_month_context"] = {
                "owner": (str(self.me["id"]), str(self.me["role"])), "month": str(today)[:7], "refresh": True}

    def submit(self, payload):
        if self.data["state"] == "cancelled":
            raise ValueError("本次操作已取消，請開始新一筆。")
        if self.data.get("payload") is not None and canonical(payload) != canonical(self.data["payload"]):
            raise ValueError("本次送出內容已固定，請查核或取消原操作後再修改。")
        if self.data["state"] == "completed":
            # 先驗同內容，再回原結果，避免把不同內容當成成功。
            if self.data.get("payload") is None:
                raise ValueError("此操作已完成；請查看原結果，不能用空白表單重新送出。")
            return SimpleNamespace(data=deepcopy(self.data["result"]))
        self.data["payload"] = deepcopy(payload)
        self.data["state"] = "uncertain"
        name = "create_purchase_idempotent" if self.kind == "purchase" else "consume_session_idempotent"
        response = self.client().rpc(name, {"p_operation_id": self.data["id"], **payload}).execute()
        self._completed(response_object(response))
        return response

    def cancel(self):
        status = response_object(self.client().rpc("cancel_operation", {
            "p_operation_id": self.data["id"], "p_kind": self.kind}).execute())
        if status.get("state") == "completed":
            self._completed(status.get("result"))
        elif status.get("state") == "cancelled":
            self.data["state"] = "cancelled"
        else:
            raise ValueError("未確認取消；原操作識別碼保留。")
        return status

    def next(self):
        if self.data["state"] not in ("completed", "cancelled"):
            raise ValueError("操作尚未確認完成或取消，不得換碼。")
        self.st.query_params[self.query_key] = str(uuid4())
        self.st.session_state.pop(self.state_key, None)
        key = "purchase_form_revision" if self.kind == "purchase" else "usage_form_revision"
        self.st.session_state[key] = self.st.session_state.get(key, 0) + 1

    def render(self):
        """回傳 True 表示應暫停新增表單，改顯示原結果或查核選項。"""
        if self.data["state"] == "new":
            return False
        st = self.st
        if self.data["state"] == "completed":
            st.success("本次購課與首期付款已完成。" if self.kind == "purchase" else "本次銷課已完成，不會重複扣堂。")
            st.caption("交易確認碼：" + str(self.data["result"]["id"]))
            if st.button("開始下一筆購課" if self.kind == "purchase" else "登錄下一筆銷課", key=self.query_key + "_next"):
                self.next()
                st.rerun()
            return True
        if self.data["state"] == "cancelled":
            st.info("本次操作已取消；延遲抵達的原請求也不會新增交易。")
            if st.button("重新填寫", key=self.query_key + "_new"):
                self.next()
                st.rerun()
            return True
        st.warning("本次操作尚未確認。請查核原結果，或使用原內容重試；不要另外建立一筆。")
        if self.data.get("error"):
            st.caption(self.data["error"])
        actions = [("查核原操作結果", "check")]
        if self.data.get("payload") is not None:
            actions.append(("使用原識別碼重試", "retry"))
        actions.append(("取消未完成操作", "cancel"))
        for label, action in actions:
            if st.button(label, key=self.query_key + "_" + action):
                try:
                    if action == "check":
                        result = self.resolve()
                        if result["state"] == "not_found":
                            st.info("目前未查到成功收據；可原碼重試，或取消後重新填寫。")
                    elif action == "retry":
                        self.submit(self.data["payload"])
                    else:
                        self.cancel()
                    st.rerun()
                except Exception as exc:
                    st.error(f"原識別碼已保留：{exc}")
        return True
