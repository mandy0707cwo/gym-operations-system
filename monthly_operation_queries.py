"""每月查詢的體驗與單次銷售明細；確認後才讀取，不寫入資料庫。"""
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from confirmed_queries import confirm_query

MONEY_COLUMN = "金額（含稅）"
REPORTS = {
    "體驗項目": ("trial_items", ["日期", "教練", "會員", "課程屬性", "項目", "內容", "時數", MONEY_COLUMN, "備註"]),
    "單次銷售": ("single_sales", ["日期", "教練", "會員", "課程屬性", "內容", "時數", MONEY_COLUMN, "備註"]),
}


def operation_report_frame(records, report_name, coach_names):
    """依使用者確認，原始 amount 已含稅，直接使用原值，不再加稅。"""
    if report_name not in REPORTS:
        raise ValueError("無效的營運報表種類。")
    result = []
    for record in records:
        amount = Decimal(str(record.get("amount") or 0))
        if not amount.is_finite():
            raise ValueError("原始金額不是有效數值，請查核資料。")
        row = {"日期": date.fromisoformat(str(record["entry_date"])),
               "教練": coach_names.get(record.get("coach_id"), "未知教練"),
               "會員": record.get("member_name") or "", "課程屬性": record.get("course_type") or "未分類",
               "內容": record.get("detail_content") or "" if report_name == "體驗項目" else record.get("content") or "",
               "時數": float(record.get("hours") or 0),
               MONEY_COLUMN: float(amount),
               "備註": record.get("note") or ""}
        if report_name == "體驗項目":
            row["項目"] = record.get("content") or ""
        result.append(row)
    return pd.DataFrame(result, columns=REPORTS[report_name][1])


def render_operation_query(me, report_name, client, paged_rows, coach_options, excel_bytes):
    if me.get("role") != "admin":
        st.warning("此頁僅限系統管理員使用。")
        return
    if report_name not in REPORTS:
        raise ValueError("無效的營運報表種類。")
    table_name = REPORTS[report_name][0]
    key = "monthly_operation_" + table_name
    coaches = coach_options()
    date_tab, cutoff_tab = st.tabs(["日期區間", "截止日期"], key=key + "_mode", on_change="rerun")
    mode = "日期區間" if date_tab.open else "截止日期"
    active = date_tab if date_tab.open else cutoff_tab
    with active:
        with st.form(key + ("_range" if mode == "日期區間" else "_cutoff"), border=False):
            prefix = key + ("_range" if mode == "日期區間" else "_cutoff")
            if mode == "日期區間":
                c1, c2 = st.columns(2)
                start = c1.date_input("開始日期", date.today().replace(day=1), key=prefix + "_start")
                end = c2.date_input("結束日期", date.today(), key=prefix + "_end")
            else:
                start = None
                end = st.date_input("截止日期", date.today(), key=prefix + "_end")
            c1, c2 = st.columns(2)
            coach = c1.selectbox("教練", ["全部教練"] + list(coaches), key=prefix + "_coach")
            member = c2.text_input("會員名稱", placeholder="可輸入完整或部分姓名", key=prefix + "_member").strip()
            submitted = st.form_submit_button("查詢", type="primary", width="stretch")
        snapshot = confirm_query(st, me, prefix, (str(start), str(end), coach, member), submitted)
        if not snapshot.ready:
            return
        if start is not None and start > end:
            snapshot.invalidate()
            st.error("開始日期不可晚於結束日期。")
            return
        selected_coach = coaches.get(coach)
        def build_query():
            fields = "id,entry_date,coach_id,member_name,course_type,content,hours,amount,note"
            if report_name == "體驗項目":
                fields += ",detail_content"
            query = client().table(table_name).select(fields).lte("entry_date", str(end))
            if start is not None:
                query = query.gte("entry_date", str(start))
            if selected_coach:
                query = query.eq("coach_id", selected_coach)
            return query.order("entry_date").order("id")
        try:
            records = snapshot.load("records", lambda: paged_rows(build_query))
            if member:
                records = [r for r in records if member.casefold() in str(r.get("member_name") or "").casefold()]
            coach_names = {value: name for name, value in coaches.items()}
            unknown_ids = sorted({r.get("coach_id") for r in records if r.get("coach_id") and r.get("coach_id") not in coach_names})
            for offset in range(0, len(unknown_ids), 150):
                chunk = unknown_ids[offset:offset + 150]
                profiles = snapshot.load("profiles", lambda: paged_rows(lambda:
                    client().table("profiles").select("id,display_name").in_("id", chunk).order("id")))
                coach_names.update({p["id"]: p.get("display_name") or "未知教練" for p in profiles})
            frame = operation_report_frame(records, report_name, coach_names)
        except Exception as exc:
            snapshot.invalidate()
            st.error(f"查詢未完成：{exc}。請重新按查詢。")
            return
        total = sum((Decimal(str(value)) for value in frame[MONEY_COLUMN]), Decimal("0"))
        total_label = "體驗總計（含稅）" if report_name == "體驗項目" else "單次銷售總計（含稅）"
        has_cents = any(Decimal(str(value)) % 1 for value in frame[MONEY_COLUMN])
        precision = 2 if has_cents else 0
        money_format = "$ %.2f" if has_cents else "$ %.0f"
        excel_money_format = '#,##0.00' if has_cents else '#,##0'
        st.metric(total_label, f"$ {total:,.{precision}f}", border=True)
        period = f"{start} 至 {end}" if start else f"截至 {end} 累計"
        st.caption(f"查詢結果：{period}｜{len(frame)} 筆。沿用原始含稅金額，不另行加稅。")
        if frame.empty:
            st.info("查無符合條件的資料。")
        st.dataframe(frame, hide_index=True, width="stretch", height="auto", row_height=28,
                     column_config={"日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
                                    MONEY_COLUMN: st.column_config.NumberColumn(format=money_format),
                                    "時數": st.column_config.NumberColumn(format="%.2f")})
        summary = pd.DataFrame([{"查詢方式": mode, "開始日期": start, "截止日期": end,
                                 "教練": coach, "會員名稱": member or "全部會員", "資料筆數": len(frame),
                                 total_label: float(total)}])
        # 沿用系統既有匯出器，確保日期／金額型別、凍結列與篩選保持一致。
        data = excel_bytes({report_name: frame, "查詢摘要": summary},
                           number_formats={MONEY_COLUMN: excel_money_format, total_label: excel_money_format, "時數": '0.00'},
                           fit_display_width=True)
        st.download_button("下載 Excel", data,
                           file_name=f"{report_name}_{start or '累計'}_{end}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key=prefix + "_download", width="stretch", on_click="ignore")
