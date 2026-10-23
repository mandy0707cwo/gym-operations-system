"""簡表查詢與明細，所有顯示均從目前已核准的快照重新計算。"""
import pandas as pd
import streamlit as st
from schedule_headcounts import GROUPS,headcounts,headcount_details
from schedule_headcount_component import count_grid


def render_headcounts(me,coaches,data,month,slots):
    def stay():st.session_state['_schedule_force_tab_'+me['id']]='已核准班表'
    prefix=f'headcount_{me["id"]}_{month}'
    context=f'{month}|whole-month-v29'
    try:result=headcounts(coaches,data,month,slots)
    except Exception as exc:st.error(f'班別人數無法確認：{exc}');return
    unknown=sum(x['available'] is None for (day,group),values in result['staff'].items() if group=='total' for x in values)
    if unknown:st.warning(f'本月有{unknown}筆「其他」未填上班時段，暫列C班待確認；相關人數顯示—，不計為可用。')
    selection_key=prefix+'_selected_'+context
    selected=st.session_state.get(selection_key)
    clicked=count_grid(result,context=context,selected=selected,key=prefix+'_grid_'+context,on_click=stay)
    if clicked is not None:
        try:
            if not isinstance(clicked,dict) or clicked.get('context')!=context:raise ValueError('查詢條件已改變，請重新點選')
            headcount_details(result,clicked)
        except ValueError as exc:st.error(str(exc))
        else:
            next_selection={k:clicked[k] for k in ('date','group')}
            if selected!=next_selection:
                st.session_state[selection_key]=next_selection
                stay()
                st.rerun()  # 同步表格選取與明細，避免仍框住上一個日期。
    st.caption('※上班人數／原排。點選後查看班別、姓名與時間。')
    st.caption('※星號【＊】代表當日非常態班(半日休、請假)')
    if selected:
        try:rows=headcount_details(result,selected)
        except ValueError as exc:st.error(str(exc));return
        st.markdown(f'**{selected["date"]}｜{GROUPS[selected["group"]]}明細**')
        if rows:st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch',column_config={'日期':st.column_config.DateColumn(format='YYYY-MM-DD')})
        else:st.info('該日該班沒有符合目前條件的已核准排班。')
