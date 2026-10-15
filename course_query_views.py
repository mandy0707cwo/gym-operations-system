"""會員課程與購課成功後的當月清單；只讀查詢，不建立購課或付款。"""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from confirmed_queries import ConfirmedQuery

COURSE_COLUMNS = ["購買_ID", "教練", "會員", "課程名稱", "成交金額", "已收金額",
                  "未收金額", "堂數", "效期", "付款", "課程狀況"]
VALID_ROLES = frozenset(("coach", "shared_coach", "manager", "admin"))


def business_today():
    """當月依台灣營業日期判定，避免雲端 UTC 跨月偏差。"""
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def course_overview_frame(balances, purchase_map, payment_map, code_map, status_label):
    result = []
    for item in balances:
        purchase_id = item["purchase_id"]
        purchase = purchase_map.get(purchase_id, {})
        payment = payment_map.get(purchase_id, {"amount": 0, "count": 0})
        total = Decimal(str(item.get("total_amount", purchase.get("total_amount")) or 0))
        received = Decimal(str(payment.get("amount") or 0))
        if not total.is_finite() or not received.is_finite():
            raise ValueError("課程金額或已收金額不是有效數值，請查核原始紀錄。")
        outstanding = total - received
        if received >= total:
            payment_status = "已付清"
        elif purchase.get("payment_plan") == "installment":
            payment_status = f'已付 {payment.get("count", 0)}/{purchase.get("installment_count") or "-"} 期'
        else:
            payment_status = "未付清"
        total_sessions = int(item.get("total_sessions", purchase.get("total_sessions")) or 0)
        used_sessions = int(item.get("used_sessions") or 0)
        result.append({
            "購買_ID": code_map.get(purchase_id, purchase_id),
            "教練": item.get("coach_name") or "未知教練", "會員": item.get("member_name") or "",
            "課程名稱": item.get("course_name") or purchase.get("course_name") or "",
            "成交金額": float(total), "已收金額": float(received), "未收金額": float(outstanding),
            "堂數": f"{used_sessions}／{total_sessions}",
            "效期": item.get("expiry_date") or purchase.get("expiry_date"),
            "付款": payment_status, "課程狀況": status_label(dict(item,
                total_sessions=total_sessions, used_sessions=used_sessions)),
        })
    frame = pd.DataFrame(result, columns=COURSE_COLUMNS)
    frame["效期"] = pd.to_datetime(frame["效期"], errors="raise").dt.date
    return frame


def show_course_overview(frame):
    config = {name: st.column_config.NumberColumn(format="$ %.0f", width=90)
              for name in ("成交金額", "已收金額", "未收金額")}
    config.update({"購買_ID": st.column_config.TextColumn(width=110),
                   "堂數": st.column_config.TextColumn(width=70),
                   "效期": st.column_config.DateColumn(format="YYYY-MM-DD", width=100),
                   "付款": st.column_config.TextColumn(width=110)})
    st.dataframe(frame, hide_index=True, width="stretch", height="auto", row_height=28,
                 column_config=config)


def render_current_month_purchases(me, client, paged_rows, coaches, code_builder, status_label):
    """只有購課與首期付款成功後才啟用；後續重跑使用私有快照。"""
    if me.get("role") not in VALID_ROLES:
        return
    state = st.session_state
    context = state.get("_purchase_month_context", {})
    owner = (str(me.get("id")), str(me.get("role")))
    today = business_today()
    if context.get("owner") != owner or context.get("month") != str(today)[:7]:
        return
    start = today.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    st.caption(f"當月購買資料（含稅）：{start} 至 {end}；依登入帳號原有可見範圍顯示。")
    refresh = st.button("重新整理當月購買資料", key="refresh_current_month_purchases")
    submitted = bool(context.pop("refresh", False)) or refresh
    snapshot = ConfirmedQuery(state, me, "current_month_purchases", (str(start), str(end)), submitted)
    if not snapshot.ready:
        st.info("購課已成功；請按「重新整理當月購買資料」取得清單，勿重複建立購課。")
        return
    try:
        def purchase_query():
            query = client().table("purchases").select(
                "id,purchase_code,member_id,coach_id,course_name,total_amount,total_sessions,"
                "purchase_date,expiry_date,payment_plan,installment_count,created_at")
            query = query.gte("purchase_date", str(start)).lte("purchase_date", str(end))
            if me["role"] == "coach":
                query = query.eq("coach_id", me["id"])
            return query.order("purchase_date", desc=True).order("id")
        purchases = snapshot.load("purchases", lambda: paged_rows(purchase_query))
        permitted = set(coaches.values())
        purchases = [p for p in purchases if p.get("coach_id") in permitted
                     and (me["role"] != "coach" or p.get("coach_id") == me["id"])]
        ids = [p["id"] for p in purchases]
        balances, payments = [], []
        # 分段查關聯資料，避免大量 UUID 造成 URL 過長；每段仍分頁取完整結果。
        for offset in range(0, len(ids), 150):
            chunk = ids[offset:offset + 150]
            balances.extend(snapshot.load("balances", lambda: paged_rows(lambda:
                client().table("purchase_balances").select("*").in_("purchase_id", chunk).order("purchase_id"))))
            payments.extend(snapshot.load("payments", lambda: paged_rows(lambda:
                client().table("purchase_payments").select("id,purchase_id,amount,installment_no")
                .in_("purchase_id", chunk).order("id"))))
        balance_map = {x["purchase_id"]: x for x in balances}
        if set(ids) - set(balance_map):
            raise ValueError("部分購課尚未取得課程餘額資料，請重新整理或由管理員查核。")
        ordered_balances = [balance_map[p["id"]] for p in purchases]
        coach_names = {value: key for key, value in coaches.items()}
        for balance in ordered_balances:
            if not balance.get("coach_name"):
                balance["coach_name"] = coach_names.get(balance.get("coach_id"), "未知教練")
        payment_map = {}
        for payment in payments:
            summary = payment_map.setdefault(payment["purchase_id"], {"amount": Decimal("0"), "count": 0})
            summary["amount"] += Decimal(str(payment.get("amount") or 0))
            summary["count"] += 1
        frame = course_overview_frame(ordered_balances, {p["id"]: p for p in purchases},
                                      payment_map, code_builder(purchases), status_label)
        if frame.empty:
            st.info("目前沒有可查看的當月購買資料。")
        else:
            show_course_overview(frame)
    except Exception as exc:
        snapshot.invalidate()
        st.warning(f"購課已成功，但當月清單讀取未完成：{exc}。請重新整理清單，勿重複建立購課。")
