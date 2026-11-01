"""營運管理兩分頁；先呈現查詢條件，確認後才讀取私有查詢快照。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from confirmed_queries import confirm_query
from operations_metrics import (ANNUAL_ROWS, OperationsMetrics, Period, annual_totals,
                                calendar_period, change_rate, comparison_periods, display_value)
from operations_repository import load_sources


def _load(me, connection_factory, key, criteria, submitted, start, end):
    snapshot = confirm_query(st, me, key, criteria, submitted)
    if not snapshot.ready:
        return None
    try:
        sources = snapshot.load('operations_sources', lambda: load_sources(connection_factory(), me, start, end))
        return OperationsMetrics(sources)
    except Exception as exc:
        snapshot.invalidate()
        st.error(f'營運資料無法完成檢核，未顯示部分合計：{exc}')
        return None


def _formula_notes():
    with st.expander('指標計算說明'):
        st.write('成交只計購課合約，依成交日期；分期續繳不重複算成交。金額沿用正式計算中心，不以總額重新除稅。')
        st.write('體驗人次包含免費及收費體驗，每筆登錄算一次；體驗成交率＝首次購買單數／金額大於0元的體驗人次，不判斷是否為同一批會員。')
        st.write('續約率＝續約課程筆數／全部堂數銷完的課程筆數；同一會員多筆分開計，逾期與退費中止不算完成。')
        st.write('兩項比率可能超過100%，不截斷；分母為0顯示「—」。銷課依入帳日期，跨月補單不回放至實際上課月份。')
        st.write('查詢結果不是結算封存；零筆代表目前可讀來源中無紀錄，不代表歷史匯入完整性已經確認。')


def annual_amount_chart(months, year, label, field):
    """每張圖僅取一個指標；月份及保存未稅金額沿用年度結果。"""
    chart_rows = [{'月份': f"{month['month']:02d}月", '金額': month['totals'][field]}
                  for month in months if month['totals'] is not None]
    return alt.Chart(pd.DataFrame(chart_rows)).mark_line(point=True).encode(
        x=alt.X('月份:O', sort=[f'{month:02d}月' for month in range(1, 13)], title='月份'),
        y=alt.Y('金額:Q', title=f'{label}（未稅／元）', axis=alt.Axis(format=',.0f'), scale=alt.Scale(zero=True)),
        tooltip=['月份:N', alt.Tooltip('金額:Q', title=f'{label}（未稅）', format=',.0f')],
    ).properties(title=f'{year}年每月{label}（未稅）', height=280)


def _annual(me, connection_factory, today):
    with st.form('operations_annual_form', border=False):
        year = int(st.number_input('年度', min_value=1901, max_value=9998, value=today.year, step=1,
                                   key='operations_annual_year'))
        submitted = st.form_submit_button('查詢', type='primary')
    selected = calendar_period('年', year)
    if selected.start > today:
        st.info('選取年度尚未開始。')
        return
    end = min(selected.end, today)
    engine = _load(me, connection_factory, 'operations_annual', (year, str(end)), submitted, selected.start, end)
    if engine is None:
        return
    try:
        months = annual_totals(engine, year, today)
    except Exception as exc:
        st.error(f'資料尚待查核，未顯示部分合計：{exc}')
        return
    st.caption(f'統計期間：{selected.start:%Y-%m-%d} ～ {end:%Y-%m-%d}｜金額：未稅、元｜尚未到來月份顯示「—」')
    table = []
    for label, field, kind in ANNUAL_ROWS:
        row = {'項目': label}
        for month in months:
            values = month['totals']
            row[f"{month['month']:02d}月"] = display_value(None if values is None else values[field], kind)
        table.append(row)
    st.dataframe(pd.DataFrame(table), hide_index=True, width='stretch', height='auto',
                 column_config={'項目': st.column_config.TextColumn(pinned=True)})
    for label, field in [('成交金額', 'sales_net'), ('銷課金額', 'usage_net')]:
        with st.container(border=True):
            st.altair_chart(annual_amount_chart(months, year, label, field), width='stretch')
    _formula_notes()


def _comparison(me, connection_factory, today):
    kind = st.segmented_control('統計期間', ['月', '季', '年', '自訂'], default='月', required=True,
                                key='operations_period_kind')
    with st.form('operations_comparison_form', border=False):
        if kind == '自訂':
            left, right = st.columns(2)
            start = left.date_input('開始日期', value=today.replace(day=1), key='operations_custom_start')
            end = right.date_input('結束日期', value=today, key='operations_custom_end')
            year = month = quarter = None
        else:
            left, right = st.columns(2)
            year = int(left.number_input('年度', min_value=1901, max_value=9998, value=today.year, step=1,
                                          key='operations_comparison_year'))
            month = right.selectbox('月份', list(range(1, 13)), index=today.month - 1,
                                     format_func=lambda value: f'{value:02d}月', key='operations_month') if kind == '月' else 1
            quarter = right.selectbox('季度', [1, 2, 3, 4], index=(today.month - 1) // 3,
                                       format_func=lambda value: f'第{value}季', key='operations_quarter') if kind == '季' else 1
        submitted = st.form_submit_button('查詢', type='primary')
    try:
        selected = Period(start, end) if kind == '自訂' else calendar_period(kind, year, month, quarter)
        periods = comparison_periods(kind, selected, today)
    except (ValueError, OverflowError) as exc:
        st.warning(str(exc))
        return
    begin = min(period.start for period in periods)
    finish = max(period.end for period in periods)
    criteria = (kind, selected.label, str(today), tuple(period.label for period in periods))
    engine = _load(me, connection_factory, 'operations_comparison', criteria, submitted, begin, finish)
    if engine is None:
        return
    try:
        current, previous, last_year = [engine.totals(period) for period in periods]
    except Exception as exc:
        st.error(f'資料尚待查核，未顯示部分合計：{exc}')
        return
    st.caption(f'本期：{periods[0].label}｜上期：{periods[1].label}｜去年同期：{periods[2].label}')
    if periods[0].end < selected.end:
        st.caption('本期尚未結束，統計至今日；比較期同步取相同日曆進度。')
    st.caption('金額為未稅整元。自訂區間的上期為緊接之前、相同天數的區間；基期為0時不計增減率。')
    for label, field, value_kind in [('成交金額', 'sales_net', 'money'), ('銷課金額', 'usage_net', 'money'),
                                     ('銷課堂數', 'usage_sessions', 'count'), ('體驗人次', 'trial_visits', 'count')]:
        with st.container(border=True):
            st.markdown(label + ('（未稅）' if value_kind == 'money' else ''))
            left, middle, right = st.columns(3)
            left.metric('本期', display_value(current[field], value_kind))
            for column, title, baseline in [(middle, '較上期', previous), (right, '較去年同期', last_year)]:
                change = change_rate(current[field], baseline[field])
                column.metric(title, '無基準' if change is None else f'{change:+.1%}')
                column.caption('比較期：' + display_value(baseline[field], value_kind))


def render_operations_overview(me, connection_factory, today=None):
    st.header('營運總覽')
    if me.get('role') not in ('manager', 'admin'):
        st.warning('此頁僅限主管與系統管理員使用。')
        return
    today = today or datetime.now(ZoneInfo('Asia/Taipei')).date()
    with st.tabs(['營運管理'])[0]:
        tabs = st.tabs(['年度總表', '同期對比'], key='operations_view', on_change='rerun')
        for label, tab in zip(['年度總表', '同期對比'], tabs):
            if tab.open:
                with tab:
                    if label == '年度總表':
                        _annual(me, connection_factory, today)
                    else:
                        _comparison(me, connection_factory, today)
