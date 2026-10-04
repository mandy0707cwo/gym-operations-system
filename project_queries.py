"""專案查詢：純計算及唯讀表單，正式資料不寫入、不推定遺失金額。"""
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd


def amount(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field}缺少有效數值，請先確認原始記錄。")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field}不是有效數值。") from exc
    if not result.is_finite():
        raise ValueError(f"{field}不是有限數值。")
    return result


def report_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"資料日期無效：{value}") from exc


def execution_report(project, entries, deposits, coach_names, tax, *, mode, end, start=None):
    """前期金額只依交易日期計算；表格金額、總計與下載來自同一份結果。"""
    if mode not in {"range", "cutoff", "unfunded"}:
        raise ValueError("不支援的專案查詢方式。")
    end = report_date(end)
    start = report_date(start) if start is not None else None
    if mode != "cutoff" and (start is None or start > end):
        raise ValueError("開始日期不可晚於結束日期。")
    stored = mode != "unfunded"
    if project["funding_type"] != ("stored" if stored else "unfunded"):
        raise ValueError("專案類型與查詢分頁不符。")
    opening_boundary = end.replace(day=1) if mode == "cutoff" else start
    history = [x for x in entries if x.get("project_id") == project["id"] and report_date(x["entry_date"]) <= end]
    opening = None
    if stored:
        prior_deposits = sum((amount(x.get("amount"), "儲值金額") for x in deposits
                              if x.get("project_id") == project["id"] and report_date(x["deposit_date"]) < opening_boundary), Decimal(0))
        prior_used = sum((amount(x.get("line_amount"), "執行金額") for x in history
                         if report_date(x["entry_date"]) < opening_boundary), Decimal(0))
        opening = prior_deposits - prior_used
    visible = [x for x in history if mode == "cutoff" or report_date(x["entry_date"]) >= start]
    visible.sort(key=lambda x: (str(x["entry_date"]), str(x.get("created_at") or ""), str(x["id"])), reverse=True)
    result = []
    gross_total = Decimal(0)
    net_total = 0
    for index, entry in enumerate(visible):
        gross = amount(entry.get("line_amount"), "執行金額")
        hours = amount(entry.get("item_hours"), "每次時數") * amount(entry.get("quantity"), "數量")
        if gross < 0 or hours <= 0:
            raise ValueError("專案執行金額不可為負數，時數須大於零。")
        net = tax(gross, "未稅")
        gross_total += gross
        net_total += net
        common = {"使用者": entry.get("person_name") or "", "時數": float(hours),
                  "金額（含稅）": float(gross), "金額（未稅）": net}
        if mode == "range":
            row = {"前期餘額": float(opening) if index == 0 else None,
                   "執行日期": report_date(entry["entry_date"]), "使用者": common["使用者"],
                   "執行項目": entry.get("item_name") or "", **common}
        elif mode == "cutoff":
            row = {"專案名稱": project["project_name"], "前期餘額": float(opening) if index == 0 else None,
                   "日期": report_date(entry["entry_date"]), "教練": coach_names.get(entry.get("coach_id"), "未指定" if not entry.get("coach_id") else "未知教練"),
                   "使用者": common["使用者"], "項目": entry.get("item_name") or "", **common}
        else:
            row = {"日期": report_date(entry["entry_date"]), "專案名稱": project["project_name"],
                   "教練": coach_names.get(entry.get("coach_id"), "未指定" if not entry.get("coach_id") else "未知教練"),
                   "使用者": common["使用者"], "項目": entry.get("item_name") or "", "時數": common["時數"],
                   "金額（含稅）": float(gross), "備註": entry.get("note") or ""}
        result.append(row)
    columns = {
        "range": ["前期餘額", "執行日期", "使用者", "執行項目", "時數", "金額（含稅）", "金額（未稅）"],
        "cutoff": ["專案名稱", "前期餘額", "日期", "教練", "使用者", "項目", "時數", "金額（含稅）", "金額（未稅）"],
        "unfunded": ["日期", "專案名稱", "教練", "使用者", "項目", "時數", "金額（含稅）", "備註"],
    }[mode]
    return {"frame": pd.DataFrame(result, columns=columns), "gross": float(gross_total), "net": net_total,
            "opening": float(opening) if opening is not None else None, "opening_boundary": opening_boundary,
            "start": start, "end": end, "project_name": project["project_name"]}


def deposit_report(project, deposits, tax, today):
    """儲值、後續儲值及負數沖銷都保留；不重複加上主檔 stored_amount。"""
    if project["funding_type"] != "stored":
        raise ValueError("只有已儲值專案可查詢儲值明細。")
    today = report_date(today)
    visible = [x for x in deposits if x.get("project_id") == project["id"] and report_date(x["deposit_date"]) <= today]
    visible.sort(key=lambda x: (str(x["deposit_date"]), str(x.get("created_at") or ""), str(x["id"])), reverse=True)
    result = []
    for entry in visible:
        gross = amount(entry.get("amount"), "儲值金額")
        kind = entry.get("transaction_type")
        if kind not in {"opening", "deposit", "reversal"} or (gross >= 0 if kind == "reversal" else gross <= 0):
            raise ValueError("儲值類型或金額正負不符，請先核對原始記錄。")
        result.append({"日期": report_date(entry["deposit_date"]), "專案": project["project_name"],
                       "類型": {"opening": "期初儲值", "deposit": "後續儲值", "reversal": "沖銷"}[kind],
                       "金額（含稅）": float(gross), "金額（未稅）": tax(gross, "未稅"), "備註": entry.get("note") or ""})
    frame = pd.DataFrame(result, columns=["日期", "專案", "類型", "金額（含稅）", "金額（未稅）", "備註"])
    return {"frame": frame, "gross": float(sum((amount(x["金額（含稅）"], "儲值金額") for x in result), Decimal(0))),
            "net": sum(x["金額（未稅）"] for x in result), "end": today, "project_name": project["project_name"]}


def render_project_queries(me, client, paged_rows, tax, excel_bytes):
    import streamlit as st

    if me.get("role") != "admin":
        st.warning("此頁僅限系統管理員使用。")
        return
    today = date.today()
    top = st.tabs(["已儲值專案", "未儲值專案"], key="project_query_funding", on_change="rerun")
    stored = top[0].open
    with top[0] if stored else top[1]:
        if stored:
            sub = st.tabs(["日期區間", "截止日期", "累計儲值金額"], key="project_query_stored_mode", on_change="rerun")
            mode = next((kind for tab, kind in zip(sub, ["range", "cutoff", "deposit"]) if tab.open), "range")
            container = sub[["range", "cutoff", "deposit"].index(mode)]
        else:
            mode = "unfunded"
            container = st.container()
        with container:
            # 下拉選單只讀主檔；執行／儲值交易資料只在送出查詢後載入。
            projects = paged_rows(lambda: client().table("projects").select("id,project_name,funding_type,stored_date")
                                  .eq("funding_type", "stored" if stored else "unfunded").order("project_name").order("id"))
            if not projects:
                st.info("尚無此類型專案。")
                return
            by_id = {x["id"]: x for x in projects}
            prefix = f"project_query_{mode}"
            with st.form(f"{prefix}_form", border=False, enter_to_submit=False):
                if mode in {"range", "unfunded"}:
                    c1, c2 = st.columns(2)
                    start = c1.date_input("開始日期", today.replace(day=1), key=f"{prefix}_start")
                    end = c2.date_input("結束日期", today, key=f"{prefix}_end")
                elif mode == "cutoff":
                    start = None
                    end = st.date_input("截止日期", today, key=f"{prefix}_end")
                else:
                    start, end = None, today
                project_id = st.selectbox("專案名稱", list(by_id), index=None, placeholder="請選擇專案",
                                          format_func=lambda value: by_id[value]["project_name"], key=f"{prefix}_project")
                submitted = st.form_submit_button("查詢", type="primary", width="stretch")
            snapshot_key = f"{prefix}_result"
            if submitted:
                st.session_state.pop(snapshot_key, None)
                if project_id not in by_id:
                    st.error("請選擇專案名稱。")
                    return
                if start is not None and start > end:
                    st.error("開始日期不可晚於結束日期。")
                    return
                try:
                    with st.spinner("正在查詢專案資料…"):
                        project = by_id[project_id]
                        deposits = []
                        if stored:
                            deposits = paged_rows(lambda: client().table("project_deposits")
                                                  .select("id,project_id,deposit_date,amount,transaction_type,note,created_at")
                                                  .eq("project_id", project_id).lte("deposit_date", str(end))
                                                  .order("deposit_date").order("created_at").order("id"))
                            if not deposits and project.get("stored_date") and report_date(project["stored_date"]) <= end:
                                raise ValueError("查無此專案的儲值交易明細，無法確認金額；請先補齊儲值紀錄。")
                        if mode == "deposit":
                            result = deposit_report(project, deposits, tax, today)
                        else:
                            def entry_query():
                                query = (client().table("project_entries")
                                         .select("id,project_id,entry_date,coach_id,person_name,item_name,item_hours,quantity,line_amount,note,created_at")
                                         .eq("project_id", project_id).lte("entry_date", str(end))
                                         .order("entry_date").order("created_at").order("id"))
                                return query.gte("entry_date", str(start)) if mode == "unfunded" else query
                            entries = paged_rows(entry_query)
                            coach_ids = sorted({x["coach_id"] for x in entries if x.get("coach_id")})
                            profiles = paged_rows(lambda: client().table("profiles").select("id,display_name")
                                                  .in_("id", coach_ids).order("id")) if coach_ids and mode != "range" else []
                            result = execution_report(project, entries, deposits, {x["id"]: x["display_name"] for x in profiles},
                                                      tax, mode=mode, start=start, end=end)
                        summary = {"專案名稱": project["project_name"], "查詢方式": {"range": "日期區間", "cutoff": "截止日期", "deposit": "累計儲值金額", "unfunded": "未儲值專案"}[mode],
                                   "開始日期": start, "截止日期": end, "金額合計（含稅）": result["gross"], "金額合計（未稅）": result["net"],
                                   "資料筆數": len(result["frame"])}
                        if stored and mode != "deposit":
                            summary["專案執行總計（含稅）"] = summary.pop("金額合計（含稅）")
                            summary["專案執行總計（未稅）"] = summary.pop("金額合計（未稅）")
                        if stored and mode != "deposit":
                            summary.update({"前期餘額（含稅）": result["opening"], "前期餘額截止日期": result["opening_boundary"] - pd.Timedelta(days=1)})
                        result["payload"] = excel_bytes({"查詢結果": result["frame"], "查詢摘要": pd.DataFrame([summary])})
                        # 只留該使用者最新查詢，避免保留過多報表與切換分頁誤讀。
                        for old_mode in ["range", "cutoff", "deposit", "unfunded"]:
                            st.session_state.pop(f"project_query_{old_mode}_result", None)
                        st.session_state[snapshot_key] = result
                except Exception as exc:
                    st.error(f"專案查詢失敗，未顯示部分結果：{exc}")
                    return
            result = st.session_state.get(snapshot_key)
            if result is None:
                st.info("請設定條件並按「查詢」；尚未載入交易資料。")
                return
            st.caption(f"查詢結果：{result['project_name']}｜{'截至 ' + str(result['end']) if result.get('start') is None else str(result['start']) + ' 至 ' + str(result['end'])}｜{len(result['frame'])} 筆。變更條件後請重新查詢。")
            if stored:
                c1, c2 = st.columns(2)
                label = "累計儲值金額" if mode == "deposit" else "專案執行總計"
                c1.metric(f"{label}（未稅）", f"$ {result['net']:,.0f}", border=True)
                c2.metric(f"{label}（含稅）", f"$ {result['gross']:,.2f}", border=True)
                if mode != "deposit":
                    st.caption(f"前期餘額（含稅）：$ {result['opening']:,.2f}；為 {result['opening_boundary']} 之前儲值扣除執行金額，不是逐筆餘額，也不列入專案執行總計。")
                    if mode == "cutoff":
                        st.caption("明細及總計包含截至截止日的全部執行紀錄；前期餘額則以截止日當月月初前計算。")
                else:
                    st.caption("截至今日的期初儲值、後續儲值及沖銷明細；沖銷以負數列示。")
            money = {x: st.column_config.NumberColumn(format="$ %.2f" if x != "金額（未稅）" else "$ %.0f")
                     for x in ["前期餘額", "金額（含稅）", "金額（未稅）"] if x in result["frame"].columns}
            if result["frame"].empty:
                st.info("查無符合條件的專案紀錄。")
            else:
                st.dataframe(result["frame"], hide_index=True, width="stretch", column_config={**money,
                             **{x: st.column_config.DateColumn(format="YYYY-MM-DD") for x in ["日期", "執行日期"] if x in result["frame"].columns}})
            st.download_button("下載 Excel", result["payload"], file_name=f"專案查詢_{mode}_{result['end']}_v1.13.1.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{prefix}_download", on_click="ignore", width="stretch")
