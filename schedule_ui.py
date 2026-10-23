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
from schedule_special import active_specials,special_projection,combined_slots
from schedule_draft import CoachDraft
from schedule_allowance import days_text


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
        original_args=pending.data['args']
        def clear_confirmed_preview():
            if original_args.get('p_action') in ('draft','draft_submit'):
                st.session_state.pop(f'_coach_draft_{me["id"]}_{original_args["p_month"]}',None)
        with st.expander('原操作內容'):
            st.code(serializable(pending.data['args']), language='json')
        try:
            with st.container(horizontal=True):
                if st.button('查核原排班操作'):
                    result = pending.resolve()
                    st.info('查核結果：'+result['state'])
                    if result['state']=='completed':clear_confirmed_preview()
                    if result['state'] != 'not_found':
                        st.rerun()
                if st.button('原碼重試排班操作'):
                    pending.send(pending.data['args'])
                    clear_confirmed_preview()
                    st.rerun()
                if st.button('取消未確認排班操作'):
                    pending.resolve(cancel=True)
                    st.rerun()
        except Exception as exc:
            st.error(str(exc))
        if pending.data:
            return
    try:
        raw_data = repo.load(month)
        special_snapshot=repo.special_load(month)
        specials=active_specials(special_snapshot,month)
        data=special_projection(raw_data,specials)
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
    days = {(x['coach_id'], x['work_date'][:10]): x for x in raw_data['days']}
    prefs = {x['coach_id']: x['base_shift'] for x in data['preferences']}
    role = me['role']
    editor_title = '排班審核' if role in REVIEWERS else '我的排班'
    leave_title='請假登錄' if role in REVIEWERS else '我的請假'
    tab_labels=[editor_title,'已核准班表']+(['排休額度設定'] if role in REVIEWERS else [])+[leave_title]
    tab_key='schedule_tab_'+me['id']
    if st.session_state.get(tab_key) not in (None,*tab_labels):st.session_state.pop(tab_key,None)
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
            try:slots=combined_slots(raw_data,repo.leave_load(month)['availability'],specials)
            except Exception as exc:
                st.error(f'請假時段讀取失敗，暫不顯示可能缺漏的共同班表：{exc}');return
            names={x['id']:x['display_name'] for x in coaches}
            if view=='班別人數':render_headcounts(me,coaches,approved_data(special_projection(raw_data,specials,for_headcount=True)),month,slots)
            else:
                frame=colored_summary_frame(coaches,approved,month,slots)
                st.table(frame,hide_index=True,width=1000,height=min(500,max(160,90+len(frame)*40)))
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
            try:
                usernames=repo.coach_usernames([x['id'] for x in choices])
            except Exception as exc:
                st.error(f'教練帳號讀取失敗，請重新載入後再審核：{exc}')
                return
            labels={x['id']:f'{str(usernames.get(x["id"]) or "").strip().upper()} {x["display_name"]}'.strip()
                    for x in choices}
            target = st.selectbox('填寫／審核對象', [x['id'] for x in choices],
                                  format_func=lambda v: labels[v],
                                  key='schedule_target_'+me['id'])
        else:
            target = me['id']
        if target not in {x['id'] for x in choices}:
            st.error('排班對象無效。')
            return
        name = next(x['display_name'] for x in choices if x['id'] == target)
        record = months.get(target, {'state': 'draft', 'revision': 0})
        state, revision = record['state'], record['revision']
        editable = can_edit(role, me['id'], target, state,record.get('coach_locked'))
        draft=CoachDraft(st.session_state,me['id'],month,revision) if role=='coach' else None
        view_days=data['days']
        if draft:
            view_days=special_projection({'days':draft.merged(raw_data['days'])},specials)['days']
        quota=allowance_banner(me,repo,month,target,view_days)
        quota_ok=quota is not None
        totals=draft.totals(quota,raw_data['days'],specials) if draft and quota_ok else None
        over=bool(totals and totals['remaining_units']<0)
        if role=='coach':
            if not quota_ok:
                st.warning('本月排休額度尚未核定，暫不能預排、儲存草稿或送出。')
            if draft.conflict:
                st.error('班表已由其他操作更新，本頁預排未覆蓋後端；請放棄本頁預排後重新載入。')
            if over:st.error(f'已超出排休額度{days_text(-totals["remaining_units"])}天，請調整後再儲存草稿或送出。')
            editable=editable and quota_ok and not draft.conflict
            if draft.dirty:
                st.caption('本頁有尚未儲存的預排，離開或重新整理可能遺失。按「儲存草稿」才正式保存；確認送出後鎖定。')
                if st.button('放棄本頁未儲存預排'):
                    draft.clear();st.rerun()
            if editable:
                days.update({(target,x['work_date']):x for x in draft.merged(raw_data['days'])})
        hint=('等待核定排休額度' if role=='coach' and not quota_ok else
              '本頁預排版本已過期，請重新載入' if draft and draft.conflict else
              '點日期更改班別' if editable else '本月已鎖定，修改請洽主管或管理者')
        st.caption(f'{name}｜{STATES[state]}｜{hint}')
        if record.get('review_reason'):
            st.info('審核說明：'+record['review_reason'])
        if role=='coach' and record.get('coach_locked'):
            st.info('本月已確認儲存，只有主管及管理者可以修改；不提供教練撤回或退回解鎖。核准後會顯示於「已核准班表」。')
        def send(action, payload=None):
            if action in ('save', 'fill', 'default','apply') and not editable:
                st.error('目前班表不可修改。')
                return
            if draft and action in ('save','apply'):
                try:draft.stage(action,payload or {},raw_data['days'])
                except ValueError as exc:st.error(str(exc));return
                st.rerun()
            if draft and action in ('draft','draft_submit') and (not editable or over):
                st.error('額度未核定、班表已鎖定／更新或已超額，不能儲存或送出。');return
            # 單日班別與備註一次送出，不另要求全頁異動原因。
            values = dict(payload or {})
            values['reason'] = values.get('note', '') if action == 'save' else ''
            args = {'p_coach_id': target, 'p_month': month, 'p_expected_revision': revision,
                    'p_action': action, 'p_payload': values}
            try:
                pending.send(args)
                if draft and action in ('draft','draft_submit'):draft.clear()
                st.session_state['_schedule_flash'] = True
                st.rerun()
            except Exception as exc:
                st.session_state['_schedule_error'] = True
                st.session_state['_schedule_error_text'] = f'排班操作未確認：{exc}'
                st.rerun()

        # 提前顯示，避免小視窗必須捲到月曆最下方才能儲存或送審。
        with st.container(horizontal=True):
            if role=='coach' and can_edit(role,me['id'],target,state,record.get('coach_locked')):
                if st.button('儲存草稿',disabled=not editable or over,
                    help='可以先儲存尚未排完整月的班表；不送審、不鎖定。超額或尚未核定額度不能儲存。'):
                    send('draft',draft.payload())
                ack=st.checkbox('已核對整月班表，確認後由主管及管理者修改',key=f'schedule_confirm_{me["id"]}_{month}_{revision}_{draft.data["epoch"]}')
                if st.button('確認送出',type='primary',disabled=not ack or not editable or over,
                    help='須填滿整月且未超額。預排與送審一次完成；送出後整月鎖定，不得撤回。自訂時段需先加入預排。'):
                    send('draft_submit',draft.payload())
            if role in REVIEWERS:
                if st.button('核准班表',disabled=state!='submitted'):
                    send('approve')
                if state in ('draft','returned') and st.button('代填完成並核准'):
                    send('manager_confirm')

        with st.container(horizontal=True, vertical_alignment='bottom'):
            base = st.selectbox('預設班別', ['A', 'B'], index=['A', 'B'].index(prefs[target]) if target in prefs else None,
                                placeholder='選A或B', key=f'schedule_base_{me["id"]}_{month}_{target}_{revision}',
                                disabled=not editable, width=130, label_visibility='collapsed')
            if st.button('套用班表', disabled=not editable or base not in FIXED,
                         help='一次儲存所選A／B預設並補齊本月空白；不覆蓋已儲存日期，週日預設例假。'):
                send('apply', {'base_shift': base})
        with st.sidebar.expander('班別與操作說明'):
            st.caption('A班09:00–18:00；B班12:00–21:00。套用只補空白，不覆蓋手動修改。週日預設例假，可自行更改。*表示尚未儲存的週日預設。格內簡稱：休＝整日休、半＝半日休、例＝例假、公＝公休、他＝其他。既有週末僅保留歷史顯示，不提供新選擇。')
            st.caption('教練須待額度核定後預排；選班別只暫留本頁，C／半日休須加入預排。按儲存草稿才保存，確認送出後鎖定；超額不能儲存或送出。主管及管理者仍可直接更正。')
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
                    special=specials.get(d.isoformat())
                    code = current.get('shift_code')
                    day_editable=editable and (role in REVIEWERS or (not special and code!='public_off'))
                    label = SHIFT_LABELS.get(code, '未填')
                    short = {'A':'A','B':'B','C':'C','full_off':'休','half_off':'半',
                             'weekend':'週','regular_off':'例','public_off':'公','other':'他'}.get(code,'未')
                    if current.get('preview') and code:
                        label += '＊'
                        short += '*'
                    if special:label=special['label'];short='特'
                    prefix = f'schedule_day_{me["id"]}_{target}_{d.isoformat()}_{revision}'+(f'_preview_{draft.data["epoch"]}' if draft else '')
                    # 格內表單只有便宜的顯示運算；開關選單不額外載入資料。
                    with st.popover(f'{d.day} {short}', key=prefix, width='stretch', wrap=False,
                                    help=f'{d.isoformat()}｜{label}'):
                        st.caption(f'{name}｜{d.isoformat()}')
                        if special:
                            st.info('統一特殊假別：'+special['label']+('（整日）' if not special.get('start_time') else f' {special["start_time"][:5]}–{special["end_time"][:5]}'))
                            st.caption('此為舊版統一設定，原班別仍保留；本版不再提供新增特殊假別設定。')
                        shift_key = prefix+'_shift'

                        def mark_choice(key=shift_key):
                            st.session_state['_schedule_quick_choice'] = (key, st.session_state[key])

                        if saved and code=='weekend':st.caption('既有週末紀錄保留；若要修改，請改選其他班別。')
                        options=tuple(x for x in EDITABLE_SHIFTS if role in REVIEWERS or x!='public_off')
                        shift = st.selectbox('班別', options,
                                             index=options.index(code) if saved and code in options else None,
                                             placeholder='請選擇班別', format_func=SHIFT_LABELS.get,
                                             key=shift_key, disabled=not day_editable, on_change=mark_choice)
                        if shift is not None and shift not in EDITABLE_SHIFTS:
                            st.error('班別無效。')
                            continue
                        event = st.session_state.get('_schedule_quick_choice')
                        if event and event[0] == shift_key:
                            st.session_state.pop('_schedule_quick_choice')
                            if role not in REVIEWERS and day_editable and shift in (*FIXED, 'full_off', 'weekend', 'regular_off', 'public_off'):
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
                                                           step=60, disabled=not day_editable)
                                end = pair[1].time_input('下班時間', value=time.fromisoformat(shown_end) if shown_end else None,
                                                         step=60, disabled=not day_editable)
                            else:
                                start = end = None
                            note = st.text_input('備註／其他班別說明', value=current.get('note', ''),
                                                 max_chars=1000, disabled=not day_editable,key=prefix+'_note_'+shift)
                            if st.form_submit_button('儲存修改' if role in REVIEWERS else '加入預排', disabled=not day_editable,key=prefix+'_save_'+shift):
                                try:
                                    payload = day_payload(d, shift, start, end, note)
                                except ValueError as exc:
                                    st.error(str(exc))
                                else:
                                    send('save', payload)
