"""以查詢輸出與匯出資料驗證購買_ID及會員、教練交叉篩選。"""
import ast
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import SimpleNamespace
import unittest

import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class Query:
    def __init__(self, records):
        self.records = list(records)

    def select(self, *_):
        return self

    def order(self, *_, **__):
        return self

    def in_(self, field, values):
        self.records = [x for x in self.records if x.get(field) in values]
        return self

    def eq(self, field, value):
        self.records = [x for x in self.records if x.get(field) == value]
        return self


class QueryTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
        page = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "general_queries_page")
        render = next(x for x in page.body if isinstance(x, ast.FunctionDef) and x.name == "render_usage_results")
        tax = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "_tax_display_amount")
        net = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "usage_net_amount")
        self.frame = None
        self.download = None
        self.metrics = {}
        tables = {
            "purchases": [
                {"id": "p1", "member_id": "m1", "course_name": "課程甲", "total_sessions": 12, "session_hours": 1},
                {"id": "p2", "member_id": "m1", "course_name": "課程乙", "total_sessions": 24, "session_hours": 0.5},
                {"id": "p3", "member_id": "m2", "course_name": "課程甲", "total_sessions": 12, "session_hours": 1},
            ],
            "session_usages": [
                {"id": "u1", "purchase_id": "p1", "coach_id": "c1", "usage_date": "2026-04-14", "session_seq": 1,
                 "deducted_amount": 1320, "deducted_net_amount": 1257},
                {"id": "u2", "purchase_id": "p1", "coach_id": "c2", "usage_date": "2026-04-21", "session_seq": 2,
                 "deducted_amount": 1320, "deducted_net_amount": 1257},
                {"id": "u3", "purchase_id": "p2", "coach_id": "c1", "usage_date": "2026-04-22", "session_seq": 1,
                 "deducted_amount": 1050, "deducted_net_amount": 1000},
                {"id": "u4", "purchase_id": "p3", "coach_id": "c1", "usage_date": "2026-04-23", "session_seq": 1,
                 "deducted_amount": 1050, "deducted_net_amount": 1000},
            ],
        }
        st = SimpleNamespace(
            columns=lambda _: [SimpleNamespace(metric=self.metric), SimpleNamespace(metric=self.metric)],
            caption=lambda *_: None, info=lambda *_: None, dataframe=self.dataframe,
            column_config=SimpleNamespace(DateColumn=lambda **_: None, NumberColumn=lambda **_: None),
        )
        namespace = {
            "pd": pd, "Decimal": Decimal, "ROUND_HALF_UP": ROUND_HALF_UP, "st": st,
            "coaches": {"教練甲": "c1", "教練乙": "c2"}, "coach_name_map": {"c1": "教練甲", "c2": "教練乙"},
            "client": lambda: SimpleNamespace(table=lambda table: Query(tables[table])),
            "paged_rows": lambda builder: builder().records,
            "member_maps": lambda: {"m1": "測試會員甲", "m2": "測試會員乙"},
            "purchase_codes": lambda: {"p1": "20260414-003", "p2": "20260414-002", "p3": "20260415-001"},
            "download_frame": self.download_frame,
        }
        exec(compile(ast.Module(body=[tax, net, render], type_ignores=[]), str(APP_PATH), "exec"), namespace)
        self.render = namespace["render_usage_results"]
        self.tax = namespace["_tax_display_amount"]

    def metric(self, label, value, **_):
        self.metrics[label] = value

    def dataframe(self, frame, **_):
        self.frame = frame

    def download_frame(self, label, frame, filename):
        self.download = frame.copy()

    def test_exact_purchase_and_export_totals(self):
        self.render(purchase_keyword=" 20260414-003 ", key="exact")
        self.assertEqual(self.frame["購買_ID"].tolist(), ["20260414-003"] * 2)
        self.assertEqual(self.metrics["銷課金額總計（含稅）"], "$ 2,640")
        self.assertEqual(self.metrics["銷課金額總計（未稅）"], "$ 2,514")
        pd.testing.assert_frame_equal(self.frame, self.download)

    def test_partial_purchase_id(self):
        self.render(purchase_keyword="20260414", key="partial")
        self.assertEqual(len(self.frame), 3)

    def test_member_coach_and_purchase_intersection(self):
        self.render(member_keyword="會員甲", coach_name="教練乙", purchase_keyword="20260414-003", key="combined")
        self.assertEqual(self.frame["教練"].tolist(), ["教練乙"])
        self.assertEqual(self.frame["銷課堂次"].tolist(), [2])

    def test_no_matching_id_has_zero_totals_and_no_export(self):
        self.render(purchase_keyword="20260414-999", key="missing")
        self.assertIsNone(self.frame)
        self.assertIsNone(self.download)
        self.assertEqual(self.metrics["銷課金額總計（含稅）"], "$ 0")

    def test_conflicting_member_has_no_result(self):
        self.render(member_keyword="會員乙", purchase_keyword="20260414-003", key="conflict")
        self.assertIsNone(self.frame)

    def test_blank_id_retains_existing_member_search(self):
        self.render(member_keyword="會員甲", purchase_keyword="", key="blank")
        self.assertEqual(len(self.frame), 3)

    def test_verified_installment_rounding_difference(self):
        # 回歸案例：三期收款逐期未稅加總，與整筆未稅差 $1。
        self.assertEqual(3 * self.tax(5280, "未稅"), 15087)
        self.assertEqual(self.tax(15840, "未稅"), 15086)


if __name__ == "__main__":
    unittest.main()
