"""可直接試操作的離線展示；禁止載入.env、正式client或秘密。"""
import streamlit as st
from datetime import date
from schedule_demo_repository import DemoRepository
from schedule_ui import render_schedule
from schedule_demo_examples import load_examples

st.set_page_config(page_title='排班管理｜獨立測試版 v1.13.29',layout='wide')
identities={'測試教練甲':{'id':'demo-a','display_name':'測試教練甲','role':'coach'},
 '測試教練乙':{'id':'demo-b','display_name':'測試教練乙','role':'coach'},
 '測試主管':{'id':'demo-manager','display_name':'測試主管','role':'manager'},
 '測試管理員':{'id':'demo-admin','display_name':'測試管理員','role':'admin'}}
with st.container(horizontal=True,vertical_alignment='center'):
    who=st.selectbox('測試身分',list(identities),width=220)
    st.caption('v1.13.29｜虛構資料、不影響線上；切換身分保留本次資料，重新整理／關閉可能清空。')
me=identities[who]
if me['role'] in ('manager','admin'):
    st.caption('審核測試：在「排班審核」選擇教練及相同月份，即可核准待審班表；退回須填原因。')
with st.expander('班別人數虛構範例（僅測試版）'):
    st.caption('可載入2位虛構教練的核准班表，示範0/2、2/2及部分請假。不覆蓋本次已有的排班資料。')
    if st.button('載入虛構人數範例'):
        try:
            today=date.today()
            month=date(int(st.session_state.get('schedule_year',today.year)),int(st.session_state.get('schedule_month',today.month)),1).isoformat()
            result=load_examples(st.session_state,month)
            st.session_state['_schedule_force_tab_'+me['id']]='已核准班表'
            st.session_state['_headcount_example_dates']=result
            st.rerun()
        except Exception as exc:st.error(str(exc))
    if st.session_state.get('_headcount_example_dates'):
        item=st.session_state['_headcount_example_dates']
        st.caption(f'整段不在班：{item["full_absence"]}；部分不在班：{item["partial_absence"]}。全部都是虛構資料。')
render_schedule(me,DemoRepository(st.session_state,me))
