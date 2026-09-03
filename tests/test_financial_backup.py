import ast
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

import pandas as pd


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
FUNCTIONS = {
    "is_magnetic_wave_course",
    "is_magnetic_wave_operation",
    "is_magnetic_wave_purchase",
    "usage_sequence_by_date",
    "course_status_label",
    "completed_purchase_ids",
    "_excel_bytes",
    "_financial_backup_frames",
    "_tax_display_amount",
    "_bonus_rule_for_date",
    "_bonus_eligibility",
    "_build_purchase_code_map",
}


def load_functions():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    module = ast.Module(body=selected, type_ignores=[])
    namespace = {
        "pd": pd,
        "date": date,
        "datetime": datetime,
        "Decimal": Decimal,
        "ROUND_HALF_UP": ROUND_HALF_UP,
        "BytesIO": BytesIO,
    }
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace


def sample_tables():
    return {
        "profiles": [{"id": "c1", "username": "coach", "display_name": "王教練", "role": "coach"}],
        "members": [{"id": "m1", "member_name": "測試會員"}],
        "course_catalog": [{"course_name": "運動訓練", "course_type": "訓練"}],
        "purchases": [{"id": "p1", "member_id": "m1", "coach_id": "c1", "course_name": "運動訓練", "total_sessions": 2,
            "session_hours": 1, "total_amount": 2100, "purchase_date": "2026-08-01", "created_at": "2026-08-01T01:00:00",
            "expiry_date": "2027-08-01", "status": "active", "payment_plan": "full", "installment_count": 1,
            "purchase_kind": "first", "referral": ""}],
        "purchase_payments": [{"purchase_id": "p1", "amount": 2100, "paid_date": "2026-08-01", "installment_no": 1}],
        "session_usages": [{"id": "u1", "purchase_id": "p1", "coach_id": "c1", "usage_date": "2026-08-02", "session_seq": 1,
            "deducted_amount": 1050, "note": ""}],
        "projects": [], "project_entries": [], "project_deposits": [], "course_terminations": [],
        "trial_items": [{"coach_id": "c1", "course_type": "體驗", "hours": 1, "amount": 500, "entry_date": "2026-08-02"}],
        "single_sales": [], "event_supports": [], "bonus_rules": [],
    }


def test_financial_backup_contains_all_report_groups_and_balances():
    ns = load_functions()
    frames = ns["_financial_backup_frames"](sample_tables())
    required = {
        "財務-成交預收總表", "財務-預收餘額明細", "財務-專案儲值狀況", "財務-專案儲值明細",
        "財務-已儲值專案", "財務-未儲值專案", "財務-體驗項目報表", "財務-單堂銷售報表",
        "財務-醫生轉介", "財務-課程屬性", "財務-銷課明細", "財務-課程中止",
        "財務-教練時數", "財務-教練營收", "財務-教練談單獎金", "財務-談單獎金總計",
        "財務-教練結單獎金", "財務-結單獎金總計",
    }
    assert required == set(frames)
    truncated_names = [name[:31] for name in frames]
    assert len(truncated_names) == len(set(truncated_names))
    balance = frames["財務-預收餘額明細"].iloc[0]
    assert balance["實際預收金額"] == 2100
    assert balance["累計銷課金額"] == 1050
    assert balance["實際預收剩餘金額"] == 1050
    assert frames["財務-體驗項目報表"].iloc[0]["未稅金額"] == 500
    coach_revenue = frames["財務-教練營收"].iloc[0]
    assert coach_revenue["體驗項目金額（未稅）"] == 476
    assert coach_revenue["金額總計（未稅）"] == 1476
    workbook = ns["_excel_bytes"](frames)
    assert len(workbook) > 1000


def test_usage_sequence_uses_chronological_order_instead_of_bad_source_sequence():
    ns = load_functions()
    usages = [
        {"id": "u10", "purchase_id": "p1", "usage_date": "2026-08-27", "created_at": "2026-08-27T08:22:24", "session_seq": 9},
        {"id": "u09", "purchase_id": "p1", "usage_date": "2026-08-13", "created_at": "2026-08-18T10:57:42", "session_seq": 15},
    ]
    for seq in range(1, 9):
        usages.append({"id": f"u{seq:02d}", "purchase_id": "p1", "usage_date": f"2026-07-{seq:02d}", "created_at": f"2026-07-{seq:02d}T08:00:00", "session_seq": seq})
    displayed = ns["usage_sequence_by_date"](usages)
    assert displayed["u09"] == 9
    assert displayed["u10"] == 10


def test_course_status_filter_labels_are_mutually_exclusive():
    status = load_functions()["course_status_label"]
    assert status({"status": "active", "used_sessions": 3, "total_sessions": 10, "remaining_sessions": 7}) == "進行中"
    assert status({"status": "completed", "used_sessions": 10, "total_sessions": 10, "remaining_sessions": 0}) == "已完成"
    assert status({"status": "expired", "used_sessions": 3, "total_sessions": 10, "remaining_sessions": 7}) == "逾期中止"
    assert status({"status": "cancelled", "used_sessions": 3, "total_sessions": 10, "remaining_sessions": 7}) == "退費中止"


def test_completed_purchase_ids_counts_only_the_final_session_once():
    completed = load_functions()["completed_purchase_ids"]
    purchases = {"p1": {"total_sessions": 2}, "p2": {"total_sessions": 3}, "p3": {"total_sessions": 0}}
    usages = [
        {"id": "u1", "purchase_id": "p1", "session_seq": 1},
        {"id": "u2", "purchase_id": "p1", "session_seq": 2},
        {"id": "u3", "purchase_id": "p1", "session_seq": 2},
        {"id": "u4", "purchase_id": "p2", "session_seq": 2},
        {"id": "u5", "purchase_id": "p3", "session_seq": 0},
    ]
    assert completed(usages, purchases) == {"p1"}


def test_magnetic_wave_operation_accepts_course_type_or_item_name():
    is_magnetic = load_functions()["is_magnetic_wave_operation"]
    assert is_magnetic({"course_type": "動磁波", "content": "初次體驗"})
    assert is_magnetic({"course_type": "體驗", "content": "動磁波體驗"})
    assert not is_magnetic({"course_type": "運動訓練", "content": "身體平衡"})


def test_magnetic_wave_purchase_accepts_course_name_or_catalog_type():
    is_magnetic = load_functions()["is_magnetic_wave_purchase"]
    assert is_magnetic({"course_name": "動磁波課程"}, {})
    assert is_magnetic({"course_name": "身體平衡"}, {"身體平衡": "動磁波"})
    assert not is_magnetic({"course_name": "運動訓練"}, {"運動訓練": "一般課程"})

