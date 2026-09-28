import os
os.environ.setdefault("APP_VERSION", "v1.12.49")

import json
import os
import re
from io import BytesIO
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


import pandas as pd
import plotly.express as px
import streamlit as st


# Streamlit Cloud redeploy trigger: 2026-09-15 v1.12.35
import streamlit.components.v1 as components
from dotenv import load_dotenv
from supabase import create_client
from supabase.lib.client_options import ClientOptions


load_dotenv()
st.set_page_config(page_title="秀傳運醫營運系統", page_icon="🏋️", layout="wide")


LABELS = {
    "operation_date":"日期", "coach_name":"教練", "classes_held":"上課堂數",
    "classes_cancelled":"上課取消堂數", "trial_visits":"體驗人次",
    "trial_conversions":"體驗成交人次", "member_name":"會員名稱",
    "trial_member_name":"體驗會員姓名", "single_sale_member_name":"單堂銷售會員姓名",
    "course_name":"課程名稱", "total_sessions":"原始堂數", "session_hours":"每堂課時數",
    "remaining_sessions":"剩餘堂數", "remaining_amount":"剩餘金額",
    "purchase_date":"成交日期", "usage_date":"銷課日期", "actual_usage_date":"實際銷課日期",
    "is_makeup_label":"補單", "session_seq":"第幾堂", "deducted_amount":"扣課金額", "deducted_net_amount":"扣課未稅金額",
    "entry_date":"日期", "content":"內容", "hours":"時數",
    "deducted_hours":"應扣除時間", "deduction_reason":"扣除原因",
    "cancel_date":"取消日期", "cancelled_sessions":"上課取消堂數", "reason":"取消原因",
    "project_name":"專案名稱", "person_name":"使用者", "item_name":"操作項目",
    "quantity":"數量", "item_hours":"每次時數", "execution_hours":"執行時數", "unit_price":"價格", "line_total":"總價",
    "funding_type":"專案類型", "stored_date":"儲值日期", "stored_amount":"儲值金額", "used_amount":"已使用金額", "remaining_amount":"剩餘金額", "line_amount":"金額", "active":"狀態",
    "trial_item_name":"體驗項目", "detail_content":"內容", "referral":"醫生轉介", "amount":"金額", "default_amount":"預設金額", "note":"備註",
