"""v1.13.14 以虛構資料驗證欄位、權限、查詢時點及含稅下載。"""
import ast
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest
from course_query_views import COURSE_COLUMNS, business_today, course_overview_frame
from monthly_operation_queries import MONEY_COLUMN, REPORTS, operation_report_frame
from test_confirmed_queries import SCRIPT as QUERY_SCRIPT
import test_purchase_installment_ui as purchase_ui
from test_purchase_installment_ui import SCRIPT as PURCHASE_SCRIPT


def status(item):
    if item.get("status") == "expired": return "逾期中止"
    if item.get("status") == "cancelled": return "退費中止"
    return "已完成" if int(item.get("remaining_sessions", 0)) <= 0 else "進行中"


def load_excel_writer():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_excel_bytes")
    scope = {"pd": pd, "BytesIO": BytesIO}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<existing-excel-writer>", "exec"), scope)
    return scope["_excel_bytes"]


class CourseOverviewTests(unittest.TestCase):
    def test_exact_columns_gross_arithmetic_and_sessions(self):
        balances = [{"purchase_id": "p", "coach_name": "虛構教練", "member_name": "虛構會員",
                     "course_name": "測試訓練", "total_amount": 10500, "used_sessions": 3,
                     "total_sessions": 10, "remaining_sessions": 7, "expiry_date": "2027-01-01"}]
        purchases = {"p": {"payment_plan": "installment", "installment_count": 3}}
        frame = course_overview_frame(balances, purchases, {"p": {"amount": 7000, "count": 2}}, {"p": "20261015-001"}, status)
        self.assertEqual(list(frame.columns), COURSE_COLUMNS)
        self.assertEqual(frame.iloc[0]["堂數"], "3／10")
        self.assertEqual(frame.iloc[0]["成交金額"], 10500)
        self.assertEqual(frame.iloc[0]["已收金額"], 7000)
        self.assertEqual(frame.iloc[0]["未收金額"], 3500)
        self.assertEqual(frame.iloc[0]["付款"], "已付 2/3 期")
        self.assertEqual(frame.iloc[0]["效期"], date(2027, 1, 1))
        self.assertNotIn("實際預收餘額", frame.columns)

    def test_paid_status_does_not_depend_on_number_of_payments(self):
        balance = {"purchase_id": "p", "total_amount": 100, "remaining_sessions": 1}
        frame = course_overview_frame([balance], {"p": {"payment_plan": "installment", "installment_count": 2}},
                                      {"p": {"amount": 100, "count": 3}}, {}, status)
        self.assertEqual(frame.iloc[0]["付款"], "已付清")
        self.assertEqual(frame.iloc[0]["未收金額"], 0)

    def test_overpayment_not_silently_hidden_and_empty_schema(self):
        frame = course_overview_frame([{"purchase_id": "p", "total_amount": 100}], {},
                                      {"p": {"amount": 110, "count": 1}}, {}, status)
        self.assertEqual(frame.iloc[0]["未收金額"], -10)
        self.assertEqual(list(course_overview_frame([], {}, {}, {}, status).columns), COURSE_COLUMNS)


class OperationReportTests(unittest.TestCase):
    def test_original_gross_amount_not_taxed_again(self):
        record = {"entry_date": "2026-10-15", "coach_id": "c", "member_name": "虛構會員",
                  "content": "測試項目", "detail_content": "詳細內容", "amount": 1050,
                  "hours": 0.5, "course_type": "恢復", "note": "測試"}
        for name in REPORTS:
            with self.subTest(name=name):
                frame = operation_report_frame([record], name, {"c": "虛構教練"})
                self.assertEqual(list(frame.columns), REPORTS[name][1])
                self.assertEqual(frame[MONEY_COLUMN].sum(), 1050)
                self.assertEqual(frame.iloc[0]["日期"], date(2026, 10, 15))
                self.assertEqual(frame.iloc[0]["內容"], "詳細內容" if name == "體驗項目" else "測試項目")
                self.assertEqual(frame.iloc[0]["時數"], 0.5)

    def test_excel_preserves_dates_numeric_totals_and_all_columns(self):
        frame = operation_report_frame([
            {"entry_date": "2026-10-01", "amount": 1050, "hours": 1},
            {"entry_date": "2026-10-02", "amount": 2100, "hours": 0.25}], "體驗項目", {})
        summary = pd.DataFrame([{"體驗總計（含稅）": frame[MONEY_COLUMN].sum()}])
        payload = load_excel_writer()({"體驗項目": frame, "查詢摘要": summary},
                                      number_formats={MONEY_COLUMN: '#,##0', "體驗總計（含稅）": '#,##0'}, fit_display_width=True)
        book = load_workbook(BytesIO(payload), data_only=False)
        sheet = book["體驗項目"]
        self.assertEqual([c.value for c in sheet[1]], REPORTS["體驗項目"][1])
        self.assertIsInstance(sheet["A2"].value, datetime)
        self.assertEqual(sheet["A2"].number_format, "yyyy-mm-dd")
        self.assertEqual(sheet["H2"].data_type, "n")
        self.assertEqual(sheet["H2"].value + sheet["H3"].value, book["查詢摘要"]["A2"].value)
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertTrue(sheet.auto_filter.ref)

    def test_invalid_amount_does_not_become_zero(self):
        with self.assertRaises(ValueError):
            operation_report_frame([{"entry_date": "2026-10-01", "amount": "NaN"}], "體驗項目", {})


# 使用真正的分頁讀取器，驗證超過單次 1000 筆仍完整；其餘為隔離假資料。
OP_SCRIPT = QUERY_SCRIPT.replace('names={"general_queries_page"', 'names={"paged_rows","general_queries_page"')
OP_SCRIPT = OP_SCRIPT.replace('def order(self,*a,**k): return self',
    'def order(self,*a,**k):\n  self.sort_fields=getattr(self,"sort_fields",[])+[a[0]]\n  self.records.sort(key=lambda x:tuple(str(x.get(f,"")) for f in self.sort_fields),reverse=k.get("desc",False)); return self')


class OperationQueryUITests(unittest.TestCase):
    def app(self, report="體驗項目", mode="日期區間", role="admin", records=None):
        app = AppTest.from_string("APP_PATH=" + repr(str(ROOT / "app.py")) + "\n" + OP_SCRIPT, default_timeout=30)
        table = REPORTS[report][0]
        for key, value in {"view": "financial", "role": role, "financial_report_view": report,
                           "monthly_operation_" + table + "_mode": mode,
                           "tables": {table: records or []}}.items():
            app.session_state[key] = value
        app.run()
        self.assertEqual(len(app.exception), 0)
        return app

    def records(self):
        return [{"id": "old", "entry_date": "2026-08-31", "coach_id": "c1", "member_name": "會員甲", "amount": 100},
                {"id": "start", "entry_date": "2026-09-01", "coach_id": "c1", "member_name": "會員甲", "amount": 1050},
                {"id": "end", "entry_date": "2026-09-30", "coach_id": "c1", "member_name": "會員乙", "amount": 2100},
                {"id": "future", "entry_date": "2026-10-01", "coach_id": "c1", "member_name": "會員甲", "amount": 5000}]

    def test_tab_order_hidden_tabs_no_data_and_no_duplicate_titles(self):
        app = self.app()
        self.assertEqual([t.label for t in app.tabs if t.label not in ("日期區間", "截止日期")],
                         ["會員報表", "其他報表", "每月報表", "體驗項目", "單次銷售", "教練查詢"])
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(app.session_state["reads"], [])
        self.assertFalse(any("每月查詢" in m.value or "**體驗項目**" in m.value for m in app.markdown))

    def test_range_boundaries_total_and_rerun_snapshot(self):
        for report in REPORTS:
            app = self.app(report, records=self.records())
            app.date_input[0].set_value(date(2026, 9, 1))
            app.date_input[1].set_value(date(2026, 9, 30))
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.dataframe[0].value[MONEY_COLUMN].tolist(), [1050, 2100])
            self.assertEqual(app.metric[0].value, "$ 3,150")
            reads = list(app.session_state["reads"])
            app.run()
            self.assertEqual(app.session_state["reads"], reads)
            self.assertEqual(len(app.get("download_button")), 1)

    def test_cutoff_has_one_date_and_includes_prior_history(self):
        for report in REPORTS:
            app = self.app(report, "截止日期", records=self.records())
            self.assertEqual([w.label for w in app.date_input], ["截止日期"])
            app.date_input[0].set_value(date(2026, 9, 30))
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.dataframe[0].value), 3)
            self.assertEqual(app.metric[0].value, "$ 3,250")

    def test_member_coach_intersection_and_no_automatic_refresh(self):
        app = self.app("體驗項目", "截止日期", records=self.records())
        app.date_input[0].set_value(date(2026, 9, 30))
        app.text_input[0].set_value("會員甲")
        app.selectbox[0].set_value("虛構教練")
        app.button[0].click().run()
        self.assertEqual(len(app.dataframe[0].value), 2)
        self.assertEqual(app.metric[0].value, "$ 1,150")
        count = len(app.session_state["reads"])
        app.text_input[0].set_value("不存在").run()
        self.assertEqual(len(app.session_state["reads"]), count)
        app.button[0].click().run()
        self.assertEqual(len(app.dataframe[0].value), 0)
        self.assertEqual(app.metric[0].value, "$ 0")

    def test_more_than_1000_records_are_not_truncated(self):
        records = [{"id": f"{n:04}", "entry_date": "2026-09-01", "coach_id": "c1", "amount": 10} for n in range(1005)]
        app = self.app("單次銷售", "截止日期", records=records)
        app.date_input[0].set_value(date(2026, 9, 30))
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.dataframe[0].value), 1005)
        self.assertEqual(app.metric[0].value, "$ 10,050")

    def test_nonadmin_cannot_read_reports(self):
        for role in ["coach", "shared_coach", "manager"]:
            app = self.app(role=role)
            self.assertEqual(app.session_state["reads"], [])
            self.assertEqual(len(app.dataframe), 0)
            self.assertEqual(len(app.warning), 1)

    def test_invalid_range_is_rejected_before_transaction_read(self):
        app = self.app(records=self.records())
        app.date_input[0].set_value(date(2026, 10, 1))
        app.date_input[1].set_value(date(2026, 9, 30))
        app.button[0].click().run()
        self.assertEqual(app.session_state["reads"], [])
        self.assertEqual(len(app.error), 1)

    def test_original_cents_are_preserved_in_total(self):
        app = self.app("體驗項目", "截止日期", records=[
            {"id": "a", "entry_date": "2026-09-01", "coach_id": "c1", "amount": 10.01},
            {"id": "b", "entry_date": "2026-09-02", "coach_id": "c1", "amount": 10.01}])
        app.date_input[0].set_value(date(2026, 9, 30))
        app.button[0].click().run()
        self.assertEqual(app.metric[0].value, "$ 20.02")
        self.assertEqual(app.dataframe[0].value[MONEY_COLUMN].tolist(), [10.01, 10.01])

    def test_coach_query_new_schema_amounts_and_filter(self):
        tables = {"purchases": [{"id": "p", "purchase_code": "20261015-001", "purchase_date": "2026-10-15",
                                 "payment_plan": "installment", "installment_count": 2}],
                  "purchase_payments": [{"id": "pay", "purchase_id": "p", "amount": 500, "installment_no": 1}],
                  "purchase_balances": [{"purchase_id": "p", "coach_id": "c1", "coach_name": "虛構教練",
                                         "member_name": "會員甲", "course_name": "測試", "total_amount": 1050,
                                         "total_sessions": 12, "used_sessions": 3, "remaining_sessions": 9,
                                         "expiry_date": "2027-10-15", "status": "active"}]}
        app = AppTest.from_string("APP_PATH=" + repr(str(ROOT / "app.py")) + "\n" + OP_SCRIPT, default_timeout=30)
        for key, value in {"view": "coach", "role": "coach", "tables": tables}.items():
            app.session_state[key] = value
        app.run()
        self.assertEqual(len(app.dataframe), 0)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        frame = app.dataframe[0].value
        self.assertEqual(list(frame.columns), COURSE_COLUMNS)
        self.assertEqual(frame.iloc[0]["堂數"], "3／12")
        self.assertEqual(frame.iloc[0]["已收金額"], 500)
        self.assertEqual(frame.iloc[0]["未收金額"], 550)


class CurrentPurchaseUITests(unittest.TestCase):
    """只執行本類新增方法，既有測試由正式回歸清單另行執行。"""
    clean = purchase_ui.PurchaseUITests.clean
    widget = purchase_ui.PurchaseUITests.widget
    fill_purchase = purchase_ui.PurchaseUITests.fill_purchase
    submit = purchase_ui.PurchaseUITests.submit
    assert_purchase_blank = purchase_ui.PurchaseUITests.assert_purchase_blank
    def app(self, role="admin", tab=None, direct=False):
        script = PURCHASE_SCRIPT.replace('st.session_state.db["purchases"].append(purchase)',
            'st.session_state.db["purchases"].append(purchase)\n'
            '   st.session_state.db["purchase_balances"].append(dict(purchase,purchase_id=purchase["id"],'
            'member_name="虛構客戶",coach_name="虛構教練",used_sessions=0,remaining_sessions=purchase["total_sessions"],status="active"))')
        app = AppTest.from_string("APP_PATH=" + repr(str(ROOT / "app.py")) + "\n" + script, default_timeout=30)
        app.session_state["role"] = role
        app.run(); self.clean(app)
        return app

    def test_success_loads_monthly_once_and_keeps_fields_blank(self):
        app = self.app()
        self.assertNotIn("purchases", app.session_state["reads"])
        self.fill_purchase(app, "分期")
        self.submit(app, "確認並建立購買紀錄")
        self.assert_purchase_blank(app)
        self.assertEqual(len(app.dataframe), 1)
        frame = app.dataframe[0].value
        self.assertEqual(list(frame.columns), COURSE_COLUMNS)
        self.assertEqual(frame.iloc[0]["已收金額"], 1050)
        self.assertEqual(frame.iloc[0]["未收金額"], 9450)
        count = len(app.session_state["reads"])
        app.run(); self.clean(app)
        self.assertNotIn("purchases", app.session_state["reads"][count:])
        self.assertEqual(len(app.session_state["writes"]), 1)

    def test_failed_purchase_does_not_enable_monthly_list(self):
        app = self.app(); self.fill_purchase(app)
        app.session_state["fail_table"] = "purchase_payments"
        self.submit(app, "確認並建立購買紀錄")
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(app.session_state["writes"], [])
        self.assertNotIn("purchases", app.session_state["reads"])

    def test_owner_isolation_after_success(self):
        app = self.app(); self.fill_purchase(app)
        self.submit(app, "確認並建立購買紀錄")
        app.session_state["role"] = "coach"
        count = len(app.session_state["reads"])
        app.run(); self.clean(app)
        self.assertEqual(len(app.dataframe), 0)
        self.assertNotIn("purchases", app.session_state["reads"][count:])

    def test_refresh_updates_payment_but_does_not_write_purchase(self):
        app = self.app(); self.fill_purchase(app, "分期")
        self.submit(app, "確認並建立購買紀錄")
        db = deepcopy(app.session_state["db"])
        db["purchase_payments"].append({"id": "later", "purchase_id": "new-1", "amount": 9450, "installment_no": 2})
        app.session_state["db"] = db
        app.button(key="refresh_current_month_purchases").click().run(); self.clean(app)
        self.assertEqual(app.dataframe[0].value.iloc[0]["已收金額"], 10500)
        self.assertEqual(app.dataframe[0].value.iloc[0]["未收金額"], 0)
        self.assertEqual(app.dataframe[0].value.iloc[0]["付款"], "已付清")
        self.assertEqual(len(app.session_state["writes"]), 1)

    def test_listing_failure_warns_without_resending_purchase(self):
        app = self.app(); self.fill_purchase(app)
        self.submit(app, "確認並建立購買紀錄")
        db = deepcopy(app.session_state["db"])
        db["purchase_balances"] = []
        app.session_state["db"] = db
        app.button(key="refresh_current_month_purchases").click().run(); self.clean(app)
        self.assertEqual(len(app.warning), 1)
        self.assertIn("購課已成功", app.warning[0].value)
        self.assertEqual(len(app.session_state["writes"]), 1)
        self.assertEqual(len(app.dataframe), 0)
        app.run(); self.clean(app)
        self.assertEqual(len(app.session_state["writes"]), 1)


if __name__ == "__main__":
    unittest.main()
