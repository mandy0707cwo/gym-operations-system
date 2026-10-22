"""以實際帳號管理函式與虛構連線驗證帶入，不存取正式Supabase。"""
import ast
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP = ROOT / ".test-temp"
TEST_TEMP.mkdir(exist_ok=True)
tempfile.tempdir = str(TEST_TEMP)
from streamlit.testing.v1 import AppTest

COACH = "00000000-0000-4000-8000-000000000001"
MANAGER = "00000000-0000-4000-8000-000000000002"
ADMIN = "00000000-0000-4000-8000-000000000003"
SHARED = "00000000-0000-4000-8000-000000000004"

SCRIPT = '''
import ast, copy, re
from pathlib import Path
import streamlit as st
ROLE_LABELS={"coach":"教練","shared_coach":"共用教練帳號","manager":"主管","admin":"系統管理員"}
USERNAME_RE=re.compile(r"[a-z0-9_]{3,30}")
st.session_state.setdefault("db",[
 {"id":"00000000-0000-4000-8000-000000000001","username":"demo_coach","display_name":"虛構教練","role":"coach","active":True},
 {"id":"00000000-0000-4000-8000-000000000002","username":"demo_manager","display_name":"虛構主管","role":"manager","active":False},
 {"id":"00000000-0000-4000-8000-000000000003","username":"demo_admin","display_name":"虛構管理員","role":"admin","active":True},
 {"id":"00000000-0000-4000-8000-000000000004","username":"demo_shared","display_name":"虛構共用帳號","role":"shared_coach","active":False}])
st.session_state.setdefault("writes",[])
st.session_state.setdefault("auth_writes",[])
st.session_state.setdefault("reads",[])
class Query:
 def __init__(self, name): self.name=name;self.payload=None;self.filters={}
 def select(self,*a,**k): return self
 def order(self,*a,**k): return self
 def eq(self,k,v): self.filters[k]=v;return self
 def limit(self,*a): return self
 def update(self,payload): self.payload=payload;return self
 def execute(self):
  if self.name!="profiles": raise AssertionError("不應讀取業務或財務資料")
  matches=[r for r in st.session_state.db if all(r.get(k)==v for k,v in self.filters.items())]
  if self.payload is not None:
   st.session_state.writes.append({"ids":[r["id"] for r in matches],"payload":copy.deepcopy(self.payload)})
   for r in matches:r.update(self.payload)
  else:st.session_state.reads.append(self.name)
  return type("Response",(),{"data":copy.deepcopy(matches)})()
class AdminAuth:
 def update_user_by_id(self,uid,payload):st.session_state.auth_writes.append({"id":uid,"payload":payload})
 def create_user(self,*a): raise AssertionError("不應建立帳號")
 def delete_user(self,*a): raise AssertionError("不應刪除帳號")
class Client:
 auth=type("Auth",(),{"admin":AdminAuth()})()
 def table(self,name): return Query(name)
def admin_client(): return Client()
def client(): raise AssertionError("不應觸發正式登入或登出")
def rows(q):return q.execute().data
def section_heading(label):st.markdown(label)
def show_table(*a):pass
node=next(n for n in ast.parse(Path(APP_PATH).read_text(encoding="utf-8")).body if isinstance(n,ast.FunctionDef) and n.name=="account_admin_page")
exec(compile(ast.Module(body=[node],type_ignores=[]),"<actual-account-admin>","exec"),globals())
me={"id":"00000000-0000-4000-8000-000000000003","username":"demo_admin","role":st.session_state.get("actor_role","admin")}
account_admin_page(me)
'''


class AccountUpdateFormTests(unittest.TestCase):
    def app(self, role="admin"):
        app = AppTest.from_string("APP_PATH=" + repr(str(ROOT / "app.py")) + "\n" + SCRIPT, default_timeout=20)
        app.session_state["actor_role"] = role
        app.run()
        self.clean(app)
        return app

    def clean(self, app):
        self.assertEqual(len(app.exception), 0)

    def widget(self, app, kind, label):
        return next(w for w in getattr(app, kind) if w.label == label)

    def select(self, app, uid):
        app.selectbox(key="account_edit_target").set_value(uid).run()
        self.clean(app)

    def role_widget(self, app):
        return next(w for w in app.selectbox if str(w.key).startswith("account_edit_role_"))

    def status_widget(self, app):
        return next(w for w in app.selectbox if str(w.key).startswith("account_edit_active_"))

    def password_widget(self, app):
        return self.widget(app,"text_input","重設密碼（留空表示不變；至少 8 碼）")

    def submit(self, app):
        self.widget(app,"button","更新帳號").click().run()
        self.clean(app)

    def test_initial_no_selection_and_no_update(self):
        app=self.app()
        self.assertIsNone(app.selectbox(key="account_edit_target").value)
        self.assertFalse(any(b.label=="更新帳號" for b in app.button))
        self.assertEqual(app.session_state["writes"],[])

    def test_all_roles_and_enabled_status_loaded_without_writes(self):
        app=self.app()
        for uid,role,active in [(COACH,"教練","啟用"),(MANAGER,"主管","停用"),(ADMIN,"系統管理員","啟用"),(SHARED,"共用教練帳號","停用")]:
            with self.subTest(uid=uid):
                self.select(app,uid)
                self.assertEqual(self.role_widget(app).value,role)
                self.assertEqual(self.status_widget(app).value,active)
                self.assertEqual(self.password_widget(app).value,"")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(app.session_state["auth_writes"],[])

    def test_identity_is_read_only_and_matches_selected(self):
        app=self.app();self.select(app,MANAGER)
        username=self.widget(app,"text_input","目前登入帳號")
        name=self.widget(app,"text_input","目前顯示姓名")
        self.assertTrue(username.disabled and name.disabled)
        self.assertEqual((username.value,name.value),("demo_manager","虛構主管"))

    def test_dirty_fields_and_password_do_not_carry_to_next_account(self):
        app=self.app();self.select(app,MANAGER)
        self.role_widget(app).set_value("系統管理員")
        self.status_widget(app).set_value("啟用")
        self.password_widget(app).set_value("fake-password-only")
        self.select(app,COACH)
        self.assertEqual(self.role_widget(app).value,"教練")
        self.assertEqual(self.status_widget(app).value,"啟用")
        self.assertEqual(self.password_widget(app).value,"")
        self.select(app,MANAGER)
        self.assertEqual(self.role_widget(app).value,"主管")
        self.assertEqual(self.status_widget(app).value,"停用")
        self.assertEqual(self.password_widget(app).value,"")
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(app.session_state["auth_writes"],[])

    def test_unchanged_submit_does_not_default_manager_to_coach(self):
        app=self.app();self.select(app,MANAGER);self.submit(app)
        self.assertEqual(app.session_state["writes"],[{"ids":[MANAGER],"payload":{"role":"manager","active":False}}])
        self.assertEqual(app.session_state["auth_writes"],[])

    def test_explicit_edits_write_only_selected_id(self):
        app=self.app();self.select(app,MANAGER)
        self.role_widget(app).set_value("教練")
        self.status_widget(app).set_value("啟用")
        self.submit(app)
        self.assertEqual(app.session_state["writes"],[{"ids":[MANAGER],"payload":{"role":"coach","active":True}}])
        self.assertEqual(app.session_state["db"][2]["role"],"admin")
        self.assertEqual(self.role_widget(app).value,"教練")

    def test_self_disable_is_blocked(self):
        app=self.app();self.select(app,ADMIN)
        self.status_widget(app).set_value("停用");self.submit(app)
        self.assertEqual(app.session_state["writes"],[])
        self.assertTrue(any("不可停用" in e.value for e in app.error))

    def test_invalid_password_is_blocked_and_blank_does_not_reset(self):
        app=self.app();self.select(app,COACH)
        self.password_widget(app).set_value("short");self.submit(app)
        self.assertEqual(app.session_state["writes"],[])
        self.assertEqual(app.session_state["auth_writes"],[])
        self.password_widget(app).set_value("");self.submit(app)
        self.assertEqual(app.session_state["auth_writes"],[])

    def test_non_admin_cannot_read_or_update_accounts(self):
        for role in ("coach","manager","shared_coach"):
            with self.subTest(role=role):
                app=self.app(role)
                self.assertEqual(app.session_state["reads"],[])
                self.assertEqual(app.session_state["writes"],[])
                self.assertFalse(any(w.label=="選擇帳號" for w in app.selectbox))

    def test_invalid_source_role_or_status_does_not_fall_back(self):
        for bad in ({"role":"unknown"},{"active":None},{"active":"false"}):
            with self.subTest(bad=bad):
                app=self.app();app.session_state["db"][1].update(bad)
                self.select(app,MANAGER)
                self.assertFalse(any(b.label=="更新帳號" for b in app.button))
                self.assertTrue(any("資料無效" in e.value for e in app.error))
                self.assertEqual(app.session_state["writes"],[])

    def test_duplicate_names_are_selected_by_unique_id(self):
        app=self.app()
        app.session_state["db"][0].update(username=None,display_name="同名虛構帳號")
        app.session_state["db"][1].update(username=None,display_name="同名虛構帳號")
        app.run();self.select(app,MANAGER)
        self.assertEqual(self.role_widget(app).value,"主管")
        self.assertEqual(self.status_widget(app).value,"停用")

    def test_source_refresh_does_not_reuse_old_form_values(self):
        app=self.app();self.select(app,COACH)
        self.password_widget(app).set_value("fake-password-only").run()
        app.session_state["db"][0].update(role="manager",active=False)
        app.run();self.clean(app)
        self.assertEqual(self.role_widget(app).value,"主管")
        self.assertEqual(self.status_widget(app).value,"停用")
        self.assertEqual(self.password_widget(app).value,"")
        self.assertEqual(app.session_state["writes"],[])

    def test_selector_is_outside_update_form(self):
        node=next(n for n in ast.parse((ROOT/"app.py").read_text(encoding="utf-8")).body if isinstance(n,ast.FunctionDef) and n.name=="account_admin_page")
        for block in (n for n in ast.walk(node) if isinstance(n,ast.With)):
            self.assertFalse(any(isinstance(c,ast.Call) and isinstance(c.func,ast.Attribute) and c.func.attr=="selectbox" and c.args and isinstance(c.args[0],ast.Constant) and c.args[0].value=="選擇帳號" for c in ast.walk(block)))

    def test_successful_mock_password_reset_clears_password_field(self):
        app=self.app();self.select(app,COACH)
        self.password_widget(app).set_value("fake-password-only");self.submit(app)
        self.assertEqual(app.session_state["auth_writes"],[{"id":COACH,"payload":{"password":"fake-password-only"}}])
        self.assertEqual(self.password_widget(app).value,"")

    def test_stale_form_submit_after_source_change_does_not_write(self):
        app=self.app();self.select(app,COACH)
        self.role_widget(app).set_value("系統管理員")
        self.widget(app,"button","更新帳號").click()
        app.session_state["db"][0].update(role="manager",active=False)
        app.run();self.clean(app)
        self.assertEqual(self.role_widget(app).value,"主管")
        self.assertEqual(app.session_state["writes"],[])

    def test_only_account_function_and_backup_version_changed(self):
        baseline=json.loads((ROOT/"tests/fixtures/account_form_v29_contract.json").read_text(encoding="utf-8"))
        new=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
        functions=lambda tree:{n.name:hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest() for n in tree.body if isinstance(n,ast.FunctionDef)}
        before,after=baseline["functions"],functions(new)
        self.assertEqual(set(before),set(after))
        self.assertEqual({n for n in before if before[n]!=after[n]},{"account_admin_page","_full_system_backup_bytes"})
        new_backup=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=="_full_system_backup_bytes")
        for n in ast.walk(new_backup):
            if isinstance(n,ast.Constant) and n.value==(ROOT/"VERSION").read_text().strip():n.value="v1.13.29"
        self.assertEqual(before["_full_system_backup_bytes"],hashlib.sha256(ast.dump(new_backup,include_attributes=False).encode()).hexdigest())
        for name in ("README.md","CHANGELOG.md","SYSTEM_DOCUMENTATION.md"):
            self.assertTrue((ROOT/name).read_text(encoding="utf-8").startswith("# "+(ROOT/"VERSION").read_text().strip()))


if __name__=="__main__":
    unittest.main(verbosity=2)
