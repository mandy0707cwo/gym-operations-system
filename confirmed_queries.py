"""查詢確認與私有結果快照；不使用跨使用者全域快取。"""
from copy import deepcopy


class ConfirmedQuery:
    def __init__(self, state, owner, key, criteria, submitted):
        self.state = state
        self.key = "_confirmed_query_" + key
        self.identity = (str(owner.get("id")), str(owner.get("role")), criteria)
        self.submitted = bool(submitted)
        self.calls = {}
        existing = state.get(self.key)
        if submitted:
            state[self.key] = {"identity": self.identity, "data": {}}
            # 每個 session 最多保留16份查詢，不跨帳號或角色共用。
            keys = [k for k in state if str(k).startswith("_confirmed_query_")]
            for old in keys[:-16]:
                state.pop(old, None)
        elif existing is not None and existing["identity"] != self.identity:
            state.pop(self.key, None)
        self.ready = self.key in state

    def load(self, key, loader):
        if not self.ready:
            raise ValueError("請先按查詢，尚未載入資料。")
        number = self.calls.get(key, 0)
        self.calls[key] = number + 1
        cache_key = (key, number)
        entry = self.state[self.key]
        if self.submitted:
            value = loader()
            entry["data"][cache_key] = deepcopy(value)
        elif cache_key not in entry["data"]:
            self.invalidate()
            raise ValueError("查詢條件或資料分支已變更，請重新按查詢。")
        return deepcopy(entry["data"][cache_key])

    def invalidate(self):
        self.state.pop(self.key, None)
        self.ready = False


def query_read(snapshot, key, loader):
    """主檔選項可即時讀取；結果資料以已確認條件的私有快照讀取。"""
    return loader() if snapshot is None else snapshot.load(key, loader)


def confirm_query(st, owner, key, criteria, submitted):
    snapshot = ConfirmedQuery(st.session_state, owner, key, criteria, submitted)
    if not snapshot.ready:
        st.info("請設定條件並按「查詢」；尚未載入查詢結果。")
    return snapshot
