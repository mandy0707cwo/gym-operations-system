"""執行方式：python -m streamlit run performance_demo.py --server.port 8519"""
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from coach_performance_ui import render_coach_performance
from performance_demo_data import PerformanceDemoClient

st.set_page_config(page_title='教練績效本機測試 v1.13.49', layout='wide')
st.warning('v1.13.49 本機測試｜全部為虛構資料，不連線正式資料庫；重新啟動或關閉分頁後工時不保留。')
label = st.sidebar.selectbox('測試角色', ['系統管理員', '主管', '教練'])
role = {'系統管理員': 'admin', '主管': 'manager', '教練': 'coach'}[label]
st.header('營運總覽／教練績效')
if role == 'coach':
    st.info('此頁僅限主管與系統管理員使用。')
else:
    render_coach_performance({'id': 'demo-' + role, 'role': role},
        lambda: PerformanceDemoClient(st.session_state, '虛構' + label), datetime.now(ZoneInfo('Asia/Taipei')).date())
