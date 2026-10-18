"""以虛構資料檢核課程預設與購課帶入，不連正式資料庫。"""
from pathlib import Path
from datetime import date, timedelta
import ast
import copy
import unittest
from streamlit.testing.v1 import AppTest
from course_defaults import catalog_default_payload, combined_purchase_note, apply_purchase_catalog_defaults
from test_purchase_installment_ui import SCRIPT

ROOT=Path(__file__).resolve().parents[1]

class CourseDefaultsTests(unittest.TestCase):
    def test_optional_blank_and_zero_validation(self):
        self.assertEqual(catalog_default_payload(None,None," "),{"default_sessions":None,"default_total_amount":None,"note":None})
        self.assertEqual(catalog_default_payload(6,8888,"測試"),{"default_sessions":6,"default_total_amount":8888.0,"note":"測試"})
        for sessions in [0,-1,1000,1.5,True,"NaN"]:
            with self.subTest(sessions=sessions), self.assertRaises(ValueError):
                catalog_default_payload(sessions,None,None)
        for amount in [0,-1,10000001,True,"NaN","Infinity","abc",1.001]:
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                catalog_default_payload(None,amount,None)

    def test_note_sources_preserved_and_empty(self):
        self.assertEqual(combined_purchase_note("客戶備註","課程備註"),"客戶備註\n課程備註")
        self.assertEqual(combined_purchase_note("客戶備註",None),"客戶備註")
        self.assertEqual(combined_purchase_note(None,"課程備註"),"課程備註")
        self.assertEqual(combined_purchase_note(None,None),"")

    def test_course_switch_resets_defaults_but_normal_rerun_preserves_edits(self):
        state={}
        member={"id":"m","note":"客戶備註"}
        course={"id":"c","default_sessions":6,"default_total_amount":8888,"note":"課程備註"}
        original=copy.deepcopy(course)
        apply_purchase_catalog_defaults(state,0,course,member)
        self.assertEqual(state["purchase_sessions_0"],6)
        self.assertEqual(state["purchase_amount_0"],8888)
        self.assertEqual(state["purchase_note_0_m"],"客戶備註\n課程備註")
        state["purchase_sessions_0"]=8
        state["purchase_amount_0"]=9000
        state["purchase_note_0_m"]="人工修改"
        apply_purchase_catalog_defaults(state,0,course,member)
        self.assertEqual(state["purchase_sessions_0"],8)
        self.assertEqual(state["purchase_amount_0"],9000)
        self.assertEqual(state["purchase_note_0_m"],"人工修改")
        apply_purchase_catalog_defaults(state,0,{"id":"blank"},member)
        self.assertIsNone(state["purchase_sessions_0"])
        self.assertIsNone(state["purchase_amount_0"])
        self.assertEqual(state["purchase_note_0_m"],"客戶備註")
        self.assertEqual(course,original)

    def test_customer_change_only_note_and_revision_blank_reset(self):
        state={}
        course={"id":"c","default_sessions":6,"default_total_amount":8888,"note":"課程"}
        apply_purchase_catalog_defaults(state,0,course,{"id":"a","note":"客戶A"})
        state["purchase_sessions_0"]=7
        apply_purchase_catalog_defaults(state,0,course,{"id":"b","note":"客戶B"})
        self.assertEqual(state["purchase_sessions_0"],7)
        self.assertEqual(state["purchase_note_0_b"],"客戶B\n課程")
        apply_purchase_catalog_defaults(state,1,None,None)
        self.assertIsNone(state["purchase_sessions_1"])
        self.assertIsNone(state["purchase_amount_1"])
        self.assertEqual(state["purchase_note_1_none"],"")

    def test_formal_functions_preserve_daily_and_atomic_rpc(self):
        version=(ROOT/"VERSION").read_text().strip()
        formal=ROOT/f"output/release_{version}/app.py"
        if not formal.exists(): formal=ROOT/"app.py"
        official=ast.parse(formal.read_text(encoding="utf-8"))
        actual=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
        of={n.name:ast.dump(n) for n in official.body if isinstance(n,ast.FunctionDef)}
        af={n.name:ast.dump(n) for n in actual.body if isinstance(n,ast.FunctionDef)}
        for name in of:
            if name!="daily_page": self.assertEqual(of[name],af[name],name)
        purchase=next(n for n in official.body if isinstance(n,ast.FunctionDef) and n.name=="course_purchase_entry")
        calls=[n for n in ast.walk(purchase) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="submit"]
        self.assertEqual(len(calls),1)
        self.assertIn('operation=Operation(st,client,me,"purchase")',formal.read_text(encoding="utf-8"))
        self.assertIn('"v1.13.19"',formal.read_text(encoding="utf-8"))

class CourseDefaultsUITests(unittest.TestCase):
    def app(self,catalog=False,role="admin"):
        app=AppTest.from_string("APP_PATH="+repr(str(ROOT/"app.py"))+"\n"+SCRIPT,default_timeout=20)
        app.session_state["role"]=role
        if catalog: app.session_state["direct_catalog"]=True
        app.run(); self.clean(app)
        return app

    def clean(self,app):
        self.assertEqual(len(app.exception),0)

    def widget(self,app,kind,label):
        return next(w for w in getattr(app,kind) if w.label==label)

    def seed(self,app):
        app.session_state["db"]["course_catalog"][0].update(default_sessions=6,default_total_amount=8888,note="課程備註")
        app.session_state["db"]["course_catalog"].append({"id":"catalog-2","course_name":"未設定課程","course_type":"訓練",
            "report_category":"測試分類","session_hours":1,"active":True,"default_sessions":None,"default_total_amount":None,"note":None})
        app.run();self.clean(app)

    def select_purchase(self,app,course="訓練｜測試課程"):
        self.widget(app,"selectbox","客戶姓名").set_value("虛構客戶｜000")
        self.widget(app,"selectbox","課程名稱").set_value(course)
        app.run();self.clean(app)

    def test_course_autofill_and_blank_switch(self):
        app=self.app();self.seed(app);self.select_purchase(app)
        self.assertEqual(self.widget(app,"number_input","課程堂數").value,6)
        self.assertEqual(self.widget(app,"number_input","成交總金額").value,8888)
        self.assertEqual(self.widget(app,"text_area","備註").value,"測試備註\n課程備註")
        self.widget(app,"selectbox","課程名稱").set_value("訓練｜未設定課程").run();self.clean(app)
        self.assertIsNone(self.widget(app,"number_input","課程堂數").value)
        self.assertIsNone(self.widget(app,"number_input","成交總金額").value)
        self.assertEqual(self.widget(app,"text_area","備註").value,"測試備註")
        self.widget(app,"selectbox","客戶姓名").set_value(None).run();self.clean(app)
        self.assertEqual(self.widget(app,"text_area","備註").value,"")
        self.assertEqual(app.session_state["writes"],[])

    def test_manual_edits_survive_unrelated_rerun(self):
        app=self.app();self.seed(app);self.select_purchase(app)
        self.widget(app,"number_input","課程堂數").set_value(7)
        self.widget(app,"number_input","成交總金額").set_value(9000)
        self.widget(app,"text_area","備註").set_value("人工修改")
        self.widget(app,"selectbox","付款方式").set_value("分期").run();self.clean(app)
        self.assertEqual(self.widget(app,"number_input","課程堂數").value,7)
        self.assertEqual(self.widget(app,"number_input","成交總金額").value,9000)
        self.assertEqual(self.widget(app,"text_area","備註").value,"人工修改")

    def test_default_purchase_snapshot_payment_and_clear(self):
        app=self.app();self.seed(app);self.select_purchase(app)
        self.widget(app,"selectbox","付款方式").set_value("未分期").run();self.clean(app)
        self.widget(app,"selectbox","購買類型").set_value("首次購買")
        self.widget(app,"date_input","購買日期").set_value(date.today())
        self.widget(app,"date_input","有效日期").set_value(date.today()+timedelta(days=90))
        original=copy.deepcopy(app.session_state["db"]["purchases"][0])
        self.widget(app,"button","確認並建立購買紀錄").click().run();self.clean(app)
        payload=app.session_state["writes"][0]["payload"]
        self.assertEqual(payload["p_purchase"]["total_sessions"],6)
        self.assertEqual(payload["p_purchase"]["total_amount"],8888)
        self.assertEqual(payload["p_first_payment"]["amount"],8888)
        self.assertEqual(payload["p_purchase"]["note"],"測試備註\n課程備註")
        self.widget(app,"button","開始下一筆購課").click().run();self.clean(app)
        self.assertIsNone(self.widget(app,"number_input","課程堂數").value)
        self.assertIsNone(self.widget(app,"number_input","成交總金額").value)
        self.assertEqual(self.widget(app,"text_area","備註").value,"")
        app.session_state["db"]["course_catalog"][0].update(default_total_amount=9999,note="後續調整")
        self.assertEqual(app.session_state["db"]["purchases"][0],original)
        self.assertEqual(app.session_state["db"]["purchases"][-1]["total_amount"],8888)
        self.assertEqual(app.session_state["db"]["purchases"][-1]["note"],"測試備註\n課程備註")

    def test_catalog_add_can_save_all_three_defaults(self):
        app=self.app(catalog=True)
        self.widget(app,"text_input","新增課程名稱").set_value("虛構新課程")
        self.widget(app,"text_input","課程屬性").set_value("訓練")
        self.widget(app,"text_input","報表分類").set_value("測試分類")
        app.number_input(key="catalog_add_sessions").set_value(6)
        app.number_input(key="catalog_add_amount").set_value(6000)
        app.text_area(key="catalog_add_note").set_value("課程說明")
        original=copy.deepcopy(app.session_state["db"]["purchases"])
        self.widget(app,"button","新增課程").click().run();self.clean(app)
        record=app.session_state["db"]["course_catalog"][-1]
        self.assertEqual(record["default_sessions"],6)
        self.assertEqual(record["default_total_amount"],6000)
        self.assertEqual(record["note"],"課程說明")
        self.assertEqual(app.session_state["db"]["purchases"],original)

    def test_catalog_clear_and_no_historical_purchase_write(self):
        app=self.app(catalog=True)
        app.session_state["db"]["course_catalog"][0].update(default_sessions=6,default_total_amount=6000,note="課程說明")
        app.run();self.clean(app)
        app.number_input(key="catalog_edit_sessions_catalog-1").set_value(None)
        app.number_input(key="catalog_edit_amount_catalog-1").set_value(None)
        app.text_area(key="catalog_edit_note_catalog-1").set_value("")
        original=copy.deepcopy(app.session_state["db"]["purchases"])
        self.widget(app,"button","儲存修改").click().run();self.clean(app)
        record=app.session_state["db"]["course_catalog"][0]
        self.assertIsNone(record["default_sessions"])
        self.assertIsNone(record["default_total_amount"])
        self.assertIsNone(record["note"])
        self.assertEqual([x["table"] for x in app.session_state["writes"]],["course_catalog"])
        self.assertEqual(app.session_state["db"]["purchases"],original)

    def test_catalog_optional_blank_and_admin_only(self):
        for role in ["coach","shared_coach","manager"]:
            with self.subTest(role=role):
                app=self.app(catalog=True,role=role)
                self.assertEqual(app.session_state["reads"],[])
                self.assertEqual(app.session_state["writes"],[])
                self.assertEqual(len(app.warning),1)
        app=self.app(catalog=True)
        self.assertIsNone(app.number_input(key="catalog_add_sessions").value)
        self.assertIsNone(app.number_input(key="catalog_add_amount").value)

    def test_missing_schema_shows_upgrade_without_writing(self):
        app=self.app(catalog=True)
        app.session_state["missing_catalog_columns"]=True
        app.run();self.clean(app)
        self.assertIn("migration_course_purchase_defaults_v1_13_10.sql",app.error[0].value)
        self.assertEqual(app.session_state["writes"],[])

if __name__=="__main__":
    unittest.main()

