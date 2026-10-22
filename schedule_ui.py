"""精簡個人月曆：日期格內改班；核准後另列共同總表。"""
import calendar
from datetime import date, time
import pandas as pd
import streamlit as st
from scheduling import (SHIFT_LABELS, FIXED, STATES, ROLES, REVIEWERS,EDITABLE_SHIFTS, can_edit,
                        day_payload, display_day, export_rows, approved_data, approved_matrix)
from schedule_repository import PendingSchedule, serializable, confirm_saved_draft
from schedule_allowance_ui import allowance_banner,allowance_settings
from schedule_leave_ui import leave_page
from schedule_summary import summary_frame,colored_summary_frame,custom_time_rows,unavailable_rows
from schedule_headcount_ui import render_headcounts


def render_schedule(me, repo, excel_bytes=None):
    if me.get('role') not in ROLES:
        st.warning('您沒有排班管理權限。')
        return
    with st.container(width=1000, gap='xsmall'):
        _render_schedule(me, repo, excel_bytes)


def _render_schedule(me, repo, excel_bytes):
    if st.session_state.pop('_schedule_error', False):
        st.error(st.session_state.pop('_schedule_error_text', '排班操作未確認。'))
    if st.session_state.pop('_schedule_flash', False):
        st.toast('排班已儲存。')
    today = date.today()
    with st.container(horizontal=True, vertical_alignment='bottom'):
        st.markdown('**排班管理**')
        year = int(st.number_input('年份', min_value=1, max_value=9998,
                                   value=today.year, key='schedule_year', width=130,
                                   label_visibility='collapsed', help='排班年份'))
        month_number = st.selectbox('月份', list(range(1, 13)), index=today.month-1,
                                    key='schedule_month', width=110, label_visibility='collapsed',
                                    format_func=lambda n:f'{n}月')
    if not 1 <= year <= 9998 or month_number not in range(1, 13):
        st.error('請選擇有效年月。')
        return
    month = date(year, month_number, 1).isoformat()
    pending = PendingSchedule(st.session_state, repo, me['id'])
    if pending.data:
        st.warning('上一筆排班操作尚未確認，請先查核、重試或取消。')
        with st.expander('原操作內容'):
            st.code(serializable(pending.data['args']), language='json')
        try:
            with st.container(horizontal=True):
                if st.button('查核原排班操作'):
                    result = pending.resolve()
                    st.info('查核結果：'+result['state'])
                    if result['state'] != 'not_found':
                        st.rerun()
                if st.button('原碼重試排班操作'):
                    pending.send(pending.data['args'])
                    st.rerun()
                if st.button('取消未確認排班操作'):
                    pending.resolve(cancel=True)
                    st.rerun()
        except Exception as exc:
            st.error(str(exc))
        if pending.data:
            return
    try:
        data = repo.load(month)
    except Exception as exc:
        st.error(f'班表讀取失敗，未顯示空白假資料：{exc}')
        return
    coaches = list(data['coaches'])
    known = {x['id'] for x in coaches}
    for item in data['months']:
        if item['coach_id'] not in known:
            coaches.append({'id': item['coach_id'], 'display_name': item['coach_name']+'（歷史）', 'active': False})
            known.add(item['coach_id'])
    if not coaches:
        st.info('目前沒有有效教練。')
        return
    months = {x['coach_id']: x for x in data['months']}
    days = {(x['coach_id'], x['work_date'][:10]): x for x in data['days']}
    prefs = {x['coach_id']: x['base_shift'] for x in data['preferences']}
    role = me['role']
    editor_title = '排班審核' if role in REVIEWERS else '我的排班'
    leave_title='請假登錄' if role in REVIEWERS else '我的請假'
    tab_labels=[editor_title,'已核准班表']+(['排休額度設定'] if role in REVIEWERS else [])+[leave_title]
    forced=st.session_state.pop('_schedule_force_tab_'+me['id'],None)
    if forced in tab_labels:st.session_state['schedule_tab_'+me['id']]=forced
    tabs = st.tabs(tab_labels,
                   key='schedule_tab_'+me['id'], on_change='rerun')
    if role in REVIEWERS and tabs[2].open:
        with tabs[2]:allowance_settings(me,repo,month,data)
        return
    if tabs[-1].open:
        with tabs[-1]:leave_page(me,repo,month,data)
        return
    if tabs[1].open:
        with tabs[1]:
            approved = approved_data(data)
            if not approved['months']:
                st.info('本月尚無已核准班表。草稿、待審與退回資料不列入總表。')
                return
            def stay_on_approved():st.session_state['_schedule_force_tab_'+me['id']]='已核准班表'
            view=st.segmented_control('班表顯示',['班別人數','教練明細'],default='班別人數',
                key='schedule_summary_view_'+me['id'],on_change=stay_on_approved)
            if view not in ('班別人數','教練明細'):
                st.info('請選擇班別人數或教練明細。');return
            try:slots=repo.leave_load(month)['availability']
            except Exception as exc:
                st.error(f'請假時段讀取失敗，暫不顯示可能缺漏的共同班表：{exc}');return
            names={x['id']:x['display_name'] for x in coaches}
            if view=='班別人數':render_headcounts(me,coaches,approved,month,slots)
            else:
                st.caption('每列一位教練、每欄一天；日期在上、星期在下。可水平捲動查看整月。')
                frame=colored_summary_frame(coaches,approved,month,slots)
                st.table(frame,hide_index=True,width=1000,height=min(500,max(160,90+len(frame)*40)))
                st.caption('藍色底＝例假，依當天已核准班別顯示，不是只看星期日。')
            st.caption('A＝09:00–18:00；B＝12:00–21:00。空白不代表休假；排班不等於實際出勤或執行時數。')
            st.caption(('＊＝另有不在班時段。' if view=='教練明細' else '＊＝半日休、其他或部分不在班。')+'展開下方查看完整時間；不公開假別、原因。班表退回後暫不列入總表。')
            with st.expander('查看上班與不在班時段'):
                custom=custom_time_rows(coaches,approved)
                if custom:
                    st.caption('自訂上班時段（C班、半日休或其他）')
                    st.dataframe(pd.DataFrame(custom),hide_index=True,width='stretch',column_config={'日期':st.column_config.DateColumn(format='YYYY-MM-DD')})
                if slots:
                    st.caption('不在班時段')
                    st.dataframe(pd.DataFrame(unavailable_rows(coaches,slots)),hide_index=True,width='stretch',column_config={
                        '日期':st.column_config.DateColumn(format='YYYY-MM-DD'),'時數':st.column_config.NumberColumn(format='%.2f')})
                if not custom and not slots:st.caption('本月無自訂上班或不在班時段。')
            if role in REVIEWERS and excel_bytes is not None:
                detail = pd.DataFrame(export_rows(coaches, approved['months'], approved['days']))
                unavailable=pd.DataFrame([{'教練':names.get(x['coach_id'],x['coach_id']),'日期':date.fromisoformat(x['work_date']),
                    '狀態':'不在班','開始':x['start_time'][:5],'結束':x['end_time'][:5],'時數':x['minutes']/60} for x in slots])
                st.download_button('下載已核准班表 Excel', excel_bytes({'排班明細': detail,'不在班時段':unavailable}),
                                   file_name=f'已核准班表_{month[:7]}.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   on_click='ignore')
        return
    with tabs[0]:
        choices = [x for x in coaches if x.get('active', True) and (role in REVIEWERS or x['id'] == me['id'])]
        if not choices:
            st.info('本帳號沒有可編輯的教練班表。')
            return
        if role in REVIEWERS:
            target = st.selectbox('填寫／審核對象', [x['id'] for x in choices],
                                  format_func=lambda v: next(x['display_name'] for x in choices if x['id'] == v),
                                  key='schedule_target_'+me['id'])
        else:
            target = me['id']
        if target not in {x['id'] for x in choices}:
            st.error('排班對象無效。')
            return
        name = next(x['display_name'] for x in choices if x['id'] == target)
        record = months.get(target, {'state': 'draft', 'revision': 0})
        state, revision = record['state'], record['revision']
        st.caption(f'{name}｜{STATES[state]}｜點日期直接更改班別')
        allowance_banner(me,repo,month,target,data['days'])
        if record.get('review_reason'):
            st.info('審核說明：'+record['review_reason'])
        if role=='coach' and state=='submitted':
            st.info('已送審，等待主管或系統管理員審核。核准後才會顯示於「已核准班表」；需修改可先撤回。')
        elif role=='coach' and state=='approved':
            st.info('班表已核准並公開於「已核准班表」。若需更改，請主管或系統管理員先退回。')
        editable = can_edit(role, me['id'], target, state)
        reason = st.text_input('主管／管理員異動原因', key=f'schedule_reason_{me["id"]}_{month}_{target}',
                               max_chars=1000) if role in REVIEWERS else ''

        def send(action, payload=None):
            if action in ('save', 'fill', 'default','apply') and not editable:
                st.error('目前班表不可修改。')
                return
            if role in REVIEWERS and action in ('save', 'fill', 'default','apply', 'return') and not reason.strip():
                st.error('主管或管理員異動須填寫原因。')
                return
            args = {'p_coach_id': target, 'p_month': month, 'p_expected_revision': revision,
                    'p_action': action, 'p_payload': dict(payload or {}, reason=reason)}
            try:
                pending.send(args)
                st.session_state['_schedule_flash'] = True
                st.rerun()
            except Exception as exc:
                st.session_state['_schedule_error'] = True
                st.session_state['_schedule_error_text'] = f'排班操作未確認：{exc}'
                st.rerun()

        # 提前顯示，避免小視窗必須捲到月曆最下方才能儲存或送審。
        with st.container(horizontal=True):
            if role=='coach' and state in ('draft','returned'):
                if st.button('儲存草稿',help='日排班會即時儲存；此鍵重新讀取並確認已儲存的日期，不送審。自訂時段／備註須先按日期格內的儲存。'):
                    try:
                        result=confirm_saved_draft(repo,month,target,revision,
                            [x for x in data['days'] if x['coach_id']==target])
                    except Exception as exc:
                        st.error(f'草稿未確認：{exc}')
                    else:
                        st.success(f'草稿已確認儲存：{result["saved_days"]}/{result["total_days"]}天，尚未送審。')
                        st.caption('日期格內尚未按「儲存時段／備註」的輸入，不包含在此次確認中。')
                if st.button('整月送審',type='primary'):
                    send('submit')
            if role=='coach' and state=='submitted':
                if st.button('撤回待審班表'):
                    send('withdraw')
            if role in REVIEWERS:
                if st.button('核准班表',disabled=state!='submitted'):
                    send('approve')
                if st.button('退回修改',disabled=state not in ('submitted','approved') or not reason.strip()):
                    send('return')

        with st.container(horizontal=True, vertical_alignment='bottom'):
            base = st.selectbox('預設班別', ['A', 'B'], index=['A', 'B'].index(prefs[target]) if target in prefs else None,
                                placeholder='選A或B', key=f'schedule_base_{me["id"]}_{month}_{target}_{revision}',
                                disabled=not editable, width=130, label_visibility='collapsed')
            if st.button('套用班表', disabled=not editable or base not in FIXED,
                         help='一次儲存所選A／B預設並補齊本月空白；不覆蓋已儲存日期，週日預設例假。'):
                send('apply', {'base_shift': base})
        with st.sidebar.expander('班別與操作說明'):
            st.caption('A班09:00–18:00；B班12:00–21:00。套用只補空白，不覆蓋手動修改。週日預設例假，可自行更改。*表示尚未儲存的週日預設。格內簡稱：休＝整日休、半＝半日休、例＝例假、公＝公休、他＝其他。既有週末僅保留歷史顯示，不提供新選擇。')
            st.caption('A／B及整日休假選好即儲存；C、半日休須填時段，其他須填說明後儲存。本版不跨日，不計薪資或實際執行時數；送審後不能直接改，無跨月鎖。')
        header = st.container(horizontal=True, gap='xsmall')
        for label in ['一', '二', '三', '四', '五', '六', '日']:
            header.container(width=80).caption('週'+label)
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month_number):
            row = st.container(horizontal=True, gap='xsmall')
            for d in week:
                with row.container(width=80):
                    if d.month != month_number:
                        st.caption('—')
                        continue
                    saved = days.get((target, d.isoformat()))
                    current = display_day(d, saved)
                    code = current.get('shift_code')
                    label = SHIFT_LABELS.get(code, '未填')
                    short = {'A':'A','B':'B','C':'C','full_off':'休','half_off':'半',
                             'weekend':'週','regular_off':'例','public_off':'公','other':'他'}.get(code,'未')
                    if current.get('preview') and code:
                        label += '＊'
                        short += '*'
                    prefix = f'schedule_day_{me["id"]}_{target}_{d.isoformat()}_{revision}'
                    # 格內表單只有便宜的顯示運算；開關選單不額外載入資料。
                    with st.popover(f'{d.day} {short}', key=prefix, width='stretch', wrap=False,
                                    help=f'{d.isoformat()}｜{label}'):
                        st.caption(f'{name}｜{d.isoformat()}')
                        shift_key = prefix+'_shift'

                        def mark_choice(key=shift_key):
                            st.session_state['_schedule_quick_choice'] = (key, st.session_state[key])

                        if saved and code=='weekend':st.caption('既有週末紀錄保留；若要修改，請改選其他班別。')
                        shift = st.selectbox('班別', EDITABLE_SHIFTS,
                                             index=EDITABLE_SHIFTS.index(code) if saved and code in EDITABLE_SHIFTS else None,
                                             placeholder='請選擇班別', format_func=SHIFT_LABELS.get,
                                             key=shift_key, disabled=not editable, on_change=mark_choice)
                        if shift is not None and shift not in EDITABLE_SHIFTS:
                            st.error('班別無效。')
                            continue
                        event = st.session_state.get('_schedule_quick_choice')
                        if event and event[0] == shift_key:
                            st.session_state.pop('_schedule_quick_choice')
                            if editable and shift in (*FIXED, 'full_off', 'weekend', 'regular_off', 'public_off'):
                                send('save', day_payload(d, shift, note=current.get('note', '')))
                        if shift is None:
                            continue
                        custom = shift in ('C', 'half_off', 'other')
                        shown_start, shown_end = (FIXED[shift] if shift in FIXED else
                                                  (current.get('start_time'), current.get('end_time')) if shift == code else (None, None))
                        if shift in FIXED:
                            st.caption('上班時段：'+'–'.join(FIXED[shift]))
                        with st.form(prefix+'_details_'+shift):
                            if custom:
                                pair = st.columns(2)
                                start = pair[0].time_input('上班時間', value=time.fromisoformat(shown_start) if shown_start else None,
                                                           step=60, disabled=not editable)
                                end = pair[1].time_input('下班時間', value=time.fromisoformat(shown_end) if shown_end else None,
                                                         step=60, disabled=not editable)
                            else:
                                start = end = None
                            note = st.text_input('備註／其他班別說明', value=current.get('note', ''),
                                                 max_chars=1000, disabled=not editable)
                            if st.form_submit_button('儲存時段／備註', disabled=not editable):
                                try:
                                    payload = day_payload(d, shift, start, end, note)
                                except ValueError as exc:
                                    st.error(str(exc))
                                else:
                                    send('save', payload)
