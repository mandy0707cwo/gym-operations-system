"""營運總覽第二分頁；查詢快照分帳號，工時寫入採版本及操作碼。"""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

import altair as alt
import pandas as pd
import streamlit as st

from coach_performance import CoachPerformance, account_sort, hours_changes
from coach_performance_repository import fetch_hours, fetch_report, require_management, save_hours
from confirmed_queries import confirm_query

SALES = [('教練', None, 'name'), ('成交金額', 'sales_net', 'money'), ('成交堂數', 'sales_sessions', 'count'),
         ('單堂平均', 'average_sale', 'money'), ('體驗人次', 'trial_visits', 'count'), ('體驗成交率', 'trial_rate', 'rate'),
         ('續課人次', 'renewal_orders', 'count'), ('續課率', 'renewal_rate', 'rate'),
         ('退費人次', 'refund_courses', 'count'), ('退費金額', 'refund_net', 'money')]
EXECUTION = [('教練', None, 'name'), ('銷課金額', 'usage_net', 'money'), ('銷課堂數', 'usage_sessions', 'count'),
             ('上課取消率', 'cancellation_rate', 'rate'), ('單次執行金額', 'oneoff_net', 'money'), ('總執行時數', 'execution_hours', 'hours')]
COMPARE = [('成交金額', 'sales_net', 'money'), ('銷課金額', 'usage_net', 'money'), ('單堂平均', 'average_sale', 'money'),
           ('總執行時數', 'execution_hours', 'hours'), ('上課取消率', 'cancellation_rate', 'rate'),
           ('銷課達成率', 'achievement_rate', 'rate'), ('體驗成交率', 'trial_rate', 'rate'),
           ('續課率', 'renewal_rate', 'rate'), ('教練會員維持率', 'retention_rate', 'rate')]
INDIVIDUAL = [COMPARE[0], COMPARE[1], COMPARE[5], COMPARE[4]]


def coach_label(row):
    return ' '.join(filter(None, [row.get('username'), row.get('display_name')]))


def local_time(value):
    return pd.Timestamp(value).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S') if value else ''


def _owner(me):
    return str(me['id']) + ':' + str(me['role'])


def _date_filters(key, today, monthly=True):
    mode = st.segmented_control('查詢方式', ['年度－月份', '日期區間'], default='年度－月份', required=True, key=key + '_mode') if monthly else '日期區間'
    return mode


def _period_fields(key, mode, today):
    a, b = st.columns(2)
    if mode == '年度－月份':
        year = int(a.number_input('年度', 1901, 9998, today.year, key=key + '_year'))
        month = int(b.selectbox('月份', list(range(1, 13)), index=today.month - 1, key=key + '_month'))
        start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    else:
        start = a.date_input('開始日期', today.replace(day=1), key=key + '_start')
        end = b.date_input('截止日期', today, key=key + '_end')
    if not isinstance(start, date) or not isinstance(end, date) or start > end or start.year < 1901 or end.year > 9998:
        raise ValueError('請輸入正確的日期區間。')
    if start > today:
        raise ValueError('查詢期間尚未開始。')
    return start, min(end, today)


def _table(engine, ids, specs):
    records = []
    for coach in engine.coaches:
        if coach['id'] not in ids:
            continue
        values = engine.totals(coach['id'])
        row = {}
        for label, field, kind in specs:
            value = values.get(field)
            if kind == 'name':
                row[label] = coach_label(coach)
            elif value is None:
                row[label] = None
            elif kind in ('money', 'count'):
                row[label] = int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
            else:
                row[label] = float(value * 100 if kind == 'rate' else value)
        records.append(row)
    frame = pd.DataFrame(records, columns=[s[0] for s in specs])
    configs = {}
    for label, _, kind in specs:
        if kind == 'name':
            configs[label] = st.column_config.TextColumn(pinned=True)
        else:
            configs[label] = st.column_config.NumberColumn(format={'money': '$ %,d', 'count': '%,d', 'rate': '%.1f%%', 'hours': '%.2f'}[kind])
    st.dataframe(frame, hide_index=True, width='stretch', column_config=configs)


def performance_chart(rows, x, label, field, kind, period, trend=False):
    data = pd.DataFrame([{x: r[x], '數值': float(r[field]) if r[field] is not None else None} for r in rows])
    unit = {'money': '未稅／元', 'hours': '小時', 'rate': '%'}[kind]
    fmt = '.1%' if kind == 'rate' else ',.0f' if kind == 'money' else ',.2f'
    chart = alt.Chart(data).mark_line(point=True) if trend else alt.Chart(data).mark_bar()
    return chart.encode(
        x=alt.X(f'{x}:O', sort=list(data[x]), title=x, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y('數值:Q', title=f'{label}（{unit}）', axis=alt.Axis(format=fmt), scale=alt.Scale(zero=True)),
        tooltip=[alt.Tooltip(f'{x}:O'), alt.Tooltip('數值:Q', title=label, format=fmt)],
    ).properties(title=f'{label}｜{period}', height=260)


def _hours_status(engine, ids):
    rows = [{'教練': coach_label(c), '上班時數': None if (v := engine.totals(c['id']))['work_hours'] is None else float(v['work_hours']),
             '狀態': v['hours_status']} for c in engine.coaches if c['id'] in ids]
    with st.expander('銷課達成率的工時檢核'):
        st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={'上班時數': st.column_config.NumberColumn(format='%.2f')})


def _notes():
    with st.expander('績效指標計算說明'):
        st.write('金額使用正式計算中心保存未稅，整元顯示；成交只計購課，分期續繳不重複算成交；單堂平均＝成交金額／成交堂數。')
        st.write('體驗人次含免費；體驗成交率＝首次購買單數／有收費體驗人次，非同一會員體驗後成交追蹤。')
        st.write('續課人次按課程筆數，續課率＝續約課程數／全部銷完課程數，不含逾期或退費中止。')
        st.write('退費人次按課程筆數；退費金額為未稅實際退費。撤銷於撤銷入帳日沖回，故單期可能為負。這不是銀行實際匯出紀錄。')
        st.write('上課取消率＝取消堂數／（銷課堂數＋取消堂數）。單次執行金額＝體驗＋單堂銷售＋專案未稅金額。')
        st.write('總執行時數＝銷課＋體驗＋單堂銷售＋專案執行時數，不含活動支援；專案為項目時數×數量。銷課含補單，依入帳日，不回放月份。這不是獎金的可計執行時數。')
        st.write('銷課達成率＝總執行時數／（手動月上班時數×80%）。只計完整月份，不按天猜算月工時；缺工時或0工時顯示無資料，不當0%。本月統計到今日，未到月底不算本月達成率。')
        st.write('會員維持率：開始日前已購課，且開始日仍未逾期、未有效中止、尚有餘堂的同教練會員，至期末仍符合者／期初會員。餘堂及中止取前一日收盤，按會員去重，新會員不進分母。')
        st.write('比率依分子分母加總，不平均每月百分比；分母0顯示「—」，成交及續課比率可能超過100%，不截斷。')


def _work_hours(me, connection_factory, today):
    # 僅在展開時查詢，避免隱藏區塊讀取資料。
    panel = st.expander('每月上班時數（主管／管理員登錄）', on_change='rerun', key='performance_hours_panel')
    if not panel.open:
        return
    owner = _owner(me)
    key = '_performance_hours:' + owner
    pending_key = key + ':pending'
    pending = st.session_state.get(pending_key)
    with panel:
        st.caption('請填扣除請假後的本月上班時數（小時），不讀取排班；空白代表未提供，0代表本月沒有上班。')
        a, b = st.columns(2)
        year = int(a.number_input('工時年度', 1901, 9998, today.year, key='performance_hours_year', disabled=bool(pending)))
        month_no = int(b.selectbox('工時月份', list(range(1, 13)), index=today.month - 1, key='performance_hours_month', disabled=bool(pending)))
        month = date(year, month_no, 1)
        load = st.button('載入／重新載入工時', disabled=bool(pending))
        if load:
            try:
                data = fetch_hours(connection_factory(), me, month)
                st.session_state[key] = {'data': data, 'generation': str(uuid4())}
            except Exception as exc:
                st.session_state.pop(key, None)
                st.error(f'工時無法載入：{exc}')
        entry = st.session_state.get(key)
        if not entry or entry['data']['month'] != str(month):
            st.info('選擇月份後按「載入／重新載入工時」。')
            return
        data = entry['data']
        coaches = sorted(data['coaches'], key=account_sort)
        if not coaches:
            st.info('沒有可登錄工時的教練。')
            return
        saved = {r['coach_id']: r for r in data['hours']}
        # ID留在伺服器索引對照，不送前台顯示。
        frame = pd.DataFrame([{'教練': coach_label(c), '上班時數': float(saved[c['id']]['minutes']) / 60 if c['id'] in saved else None,
                               '更新時間（台灣）': local_time(saved.get(c['id'], {}).get('updated_at', '')),
                               '登錄者': saved.get(c['id'], {}).get('updated_by_name', '')} for c in coaches])
        frame['上班時數'] = pd.to_numeric(frame['上班時數'], errors='raise').astype('float64')
        edited = st.data_editor(frame, hide_index=True, num_rows='fixed', disabled=True if pending else ['教練', '更新時間（台灣）', '登錄者'],
            key='performance_hours_editor:' + owner + ':' + entry['generation'],
            column_config={'上班時數': st.column_config.NumberColumn(format='%.2f', min_value=0., max_value=monthrange(year, month_no)[1] * 24., step=0.25)})
        if pending:
            st.warning('上次儲存結果尚未確認。重試會沿用相同操作，不會重複建立。')
            send = st.button('重試同一次工時儲存', type='primary')
            if st.button('重新查核工時（放棄重試）'):
                st.session_state.pop(pending_key, None)
                st.session_state.pop(key, None)
                st.rerun()
        else:
            send = st.button('儲存每月工時', type='primary')
            if send:
                try:
                    rows = hours_changes(month, coaches, data['hours'], [{'coach_id': c['id'], 'hours': edited.iloc[i]['上班時數']} for i, c in enumerate(coaches)])
                    if not rows:
                        st.info('沒有需要儲存的變更。')
                        return
                    pending = {'id': str(uuid4()), 'month': month, 'rows': rows}
                    st.session_state[pending_key] = pending
                except Exception as exc:
                    st.error(str(exc))
                    return
        if send:
            try:
                fresh = save_hours(connection_factory(), me, pending['id'], pending['month'], pending['rows'])
                st.session_state[key] = {'data': fresh, 'generation': str(uuid4())}
                st.session_state.pop(pending_key, None)
                for cache_key in list(st.session_state):
                    if cache_key.startswith('_confirmed_query_performance_'):
                        st.session_state.pop(cache_key, None)
                st.session_state['_performance_saved:' + owner] = True
                st.rerun()
            except Exception as exc:
                st.error(f'工時儲存結果尚待確認：{exc}。請重試；若提示版本衝突，重新查核後再編輯。')


def render_coach_performance(me, connection_factory, today):
    require_management(me)
    if st.session_state.pop('_performance_saved:' + _owner(me), False):
        st.success('每月工時已儲存；請重新查詢績效以套用新工時。')
    tabs = st.tabs(['績效總表', '教練對比', '個別教練績效'], key='performance_view', on_change='rerun')
    for index, tab in enumerate(tabs):
        if not tab.open:
            continue
        with tab:
            if index == 0:
                _work_hours(me, connection_factory, today)
            # 下拉只讀名單；實績必須按查詢。快照不跨帳號或角色。
            roster_key = '_performance_roster:' + _owner(me)
            try:
                if roster_key not in st.session_state:
                    st.session_state[roster_key] = fetch_hours(connection_factory(), me, today.replace(day=1))['coaches']
                coaches = sorted(st.session_state[roster_key], key=account_sort)
            except Exception:
                st.error('教練績效資料介面尚未就緒，請確認已完成 v1.13.49 資料庫升級；不影響原營運管理。')
                return
            if not coaches:
                st.info('沒有教練資料。')
                return
            key = f'performance_{index}'
            mode = _date_filters(key, today, monthly=index != 2)
            with st.form(key + '_form', border=False):
                error = None
                try:
                    start, end = _period_fields(key, mode, today)
                except ValueError as exc:
                    error = str(exc)
                labels = {c['id']: coach_label(c) for c in coaches}
                if index == 0:
                    selected = st.multiselect('教練（空白為全部）', list(labels), format_func=labels.get, key=key + '_coaches')
                elif index == 2:
                    selected = [st.selectbox('教練', list(labels), format_func=labels.get, key=key + '_coach')]
                else:
                    selected = []
                submitted = st.form_submit_button('查詢', type='primary')
            if error:
                st.warning(error)
                return
            if any(c not in labels for c in selected):
                st.error('教練選擇無效，請重新選擇。')
                return
            snap = confirm_query(st, me, key, (str(start), str(end), tuple(selected)), submitted)
            if not snap.ready:
                return
            try:
                raw = snap.load('report', lambda: fetch_report(connection_factory(), me, start, end))
                engine = CoachPerformance(raw, start, end)
                ids = set(selected) if selected else engine.ids
                st.caption(f'統計期間：{start:%Y-%m-%d} ～ {end:%Y-%m-%d}｜金額：未稅、元（無小數）｜時數：小時')
                if index == 0:
                    st.subheader('成交')
                    _table(engine, ids, SALES)
                    st.subheader('執行')
                    _table(engine, ids, EXECUTION)
                elif index == 1:
                    rows = [{'教練': coach_label(c), **engine.totals(c['id'])} for c in engine.coaches]
                    for label, field, kind in COMPARE:
                        with st.container(border=True):
                            st.altair_chart(performance_chart(rows, '教練', label, field, kind, f'{start}～{end}'))
                            if all(r[field] is None for r in rows):
                                st.caption('本指標沒有可計算的分母或完整工時，不繪製0值。')
                else:
                    rows = engine.monthly(selected[0])
                    for label, field, kind in INDIVIDUAL:
                        with st.container(border=True):
                            st.altair_chart(performance_chart(rows, '月份', label, field, kind, labels[selected[0]], trend=True))
                _hours_status(engine, ids)
                _notes()
            except Exception as exc:
                snap.invalidate()
                st.error(f'績效資料無法完成檢核，請重新查詢或由管理員查核：{exc}')
