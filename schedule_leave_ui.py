"""請假獨立登錄與稽核；全體班表只取得不在班時段。"""
from datetime import date,time
from uuid import uuid4
import calendar
import pandas as pd
import streamlit as st
from scheduling import REVIEWERS
from schedule_leave import LEAVE_TYPES,leave_payload
from schedule_leave_repository import PendingLeave


def leave_page(me,repo,month,data):
    reviewer=me['role'] in REVIEWERS
    title='請假登錄' if reviewer else '我的請假'
    if st.session_state.pop('_leave_reset_'+me['id'],False):
        st.session_state.pop('leave_selection_'+me['id']+'_v34',None)
    def stay():st.session_state['_schedule_force_tab_'+me['id']]=title
    def reset_confirmed():
        st.session_state['_leave_reset_'+me['id']]=True
        st.session_state['_leave_epoch_'+me['id']]=st.session_state.get('_leave_epoch_'+me['id'],0)+1
        st.session_state['_leave_flash_'+me['id']]=True
        stay()
    pending=PendingLeave(st.session_state,repo,me['id'])
    if pending.data:
        st.warning('上一筆請假操作尚未確認，請先查核、原碼重試或取消。')
        try:
            with st.container(horizontal=True):
                if st.button('查核請假操作',on_click=stay):
                    reply=pending.resolve();st.info('查核結果：'+reply['state'])
                    if reply['state']=='completed':reset_confirmed();st.rerun()
                    if reply['state']=='cancelled':st.rerun()
                if st.button('原碼重試請假操作',on_click=stay):pending.send(pending.data['args']);reset_confirmed();st.rerun()
                if st.button('取消未確認請假操作',on_click=stay):pending.resolve(True);st.rerun()
        except Exception as exc:st.error(str(exc))
        if pending.data:return
    try:loaded=repo.leave_load(month)
    except Exception as exc:
        st.error(f'請假資料讀取失敗，不能當作無請假：{exc}');return
    records=loaded['records'];names={x['id']:x['display_name'] for x in data['coaches']}
    st.caption('其他請假不扣每月排休額度，不計薪資、出勤或銷課達成率。登錄以單日、分鐘為單位，跨日請分筆填寫。')
    if st.session_state.pop('_leave_flash_'+me['id'],False):st.success('請假操作已確認，紀錄與異動原因已保存。')
    rows=[{'日期':date.fromisoformat(x['work_date']),'教練':names.get(x['coach_id'],x['coach_id']),
        '假別':LEAVE_TYPES[x['leave_kind']],'開始':x['start_time'][:5],'結束':x['end_time'][:5],
        '時數':x['minutes']/60,'狀態':'有效' if x['state']=='active' else '已作廢',
        '登錄／修改原因':x['reason'],'最後操作人':x['actor_name'],
        '修改時間（台灣）':pd.to_datetime(x['updated_at'],utc=True).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S')}
        for x in sorted(records,key=lambda x:(x['work_date'],x['start_time'],x['id']))]
    if rows:st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch',column_config={
        '日期':st.column_config.DateColumn(format='YYYY-MM-DD'),'時數':st.column_config.NumberColumn(format='%.2f')})
    else:st.info('本月沒有您有權查看的請假紀錄。')
    if reviewer:
        coaches=[x for x in data['coaches'] if x.get('active',True)]
        if not coaches:return
        target=st.selectbox('請假教練',[x['id'] for x in coaches],format_func=names.get,key='leave_coach_'+me['id'],on_change=stay)
        if target not in {x['id'] for x in coaches}:st.error('請假對象無效');return
        # ID仍為選擇值；畫面只顯示日期、時段及假別，不能以顯示文字當資料識別。
        options={None:None}
        labels={None:'新增請假'}
        for x in records:
            if x['coach_id']==target and x['state']=='active':
                options[x['id']]=x
                labels[x['id']]=f'{x["work_date"]} {x["start_time"][:5]}–{x["end_time"][:5]} {LEAVE_TYPES[x["leave_kind"]]}'
        selected=st.selectbox('新增／修改紀錄',list(options),format_func=labels.get,
            key='leave_selection_'+me['id']+'_v34',on_change=stay)
        if selected not in options:st.error('請假紀錄無效');return
        old=options[selected];rev=old['revision'] if old else 0
        epoch=st.session_state.get('_leave_epoch_'+me['id'],0)
        key=f'leave_form_{me["id"]}_{target}_{month}_{old["id"] if old else "new"}_{rev}_{epoch}'
        current=next((x for x in data['months'] if x['coach_id']==target),None)
        if not current or current['state']!='approved':st.warning('新增／修改請假須先核准本月班表；既有請假仍可作廢。')
        with st.form(key):
            d=st.date_input('請假日期',value=date.fromisoformat(old['work_date']) if old else None,
                min_value=date.fromisoformat(month),max_value=date.fromisoformat(month).replace(day=calendar.monthrange(int(month[:4]),int(month[5:7]))[1]),format='YYYY-MM-DD')
            kind=st.selectbox('假別',list(LEAVE_TYPES),index=list(LEAVE_TYPES).index(old['leave_kind']) if old else None,format_func=LEAVE_TYPES.get)
            with st.container(horizontal=True):
                start=st.time_input('請假開始',value=time.fromisoformat(old['start_time']) if old else None,step=60)
                end=st.time_input('請假結束',value=time.fromisoformat(old['end_time']) if old else None,step=60)
            st.caption('時數由起訖時間自動計算；不另輸入時數，避免兩者不一致。')
            reason=st.text_input('登錄／修改原因',max_chars=1000)
            confirm=st.checkbox('已確認請假時段及原因，登錄後立即生效')
            save=st.form_submit_button('確認儲存請假',on_click=stay)
            void=st.form_submit_button('作廢所選請假',disabled=old is None,on_click=stay)
            if save or void:
                if not confirm:st.error('請先勾選確認，資料未儲存');return
                try:
                    if void:
                        if not old:raise ValueError('請先選擇既有請假')
                        if not reason.strip() or len(reason.strip())>1000:raise ValueError('請填寫作廢原因')
                        payload={'reason':reason.strip()}
                    else:
                        payload=leave_payload(month,{'work_date':d,'leave_kind':kind,'start_time':start,'end_time':end,'reason':reason})
                    args={'p_id':old['id'] if old else str(uuid4()),'p_coach_id':target,'p_month':month,
                        'p_expected_revision':rev,'p_schedule_revision':current['revision'] if current else 0,
                        'p_action':'void' if void else 'save','p_payload':payload}
                    pending.send(args)
                    reset_confirmed();st.rerun()
                except Exception as exc:st.error(f'請假操作未確認：{exc}。請先查核原操作；未確認前不另建新筆。')
