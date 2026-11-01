"""純虛構本機營運管理展示；不匯入Supabase、不取得正式憑證。"""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from operations_ui import render_operations_overview


class DemoQuery:
    def __init__(self, records):
        self.records = deepcopy(records)
    def select(self, *args):
        return self
    def order(self, field):
        self.records.sort(key=lambda row: str(row.get(field, '')))
        return self
    def lte(self, field, value):
        self.records = [row for row in self.records if row[field] <= value]
        return self
    def gte(self, field, value):
        self.records = [row for row in self.records if row[field] >= value]
        return self
    def range(self, start, end):
        self.records = self.records[start:end + 1]
        return self
    def execute(self):
        return type('Result', (), {'data': self.records})()


class DemoClient:
    def __init__(self, year):
        self.tables = {'purchases': [], 'session_usages': [], 'trial_items': [], 'course_terminations': []}
        for sample_year in (year - 1, year):
            for month in range(1, 13):
                stamp = f'{sample_year}-{month:02d}'
                for number in range(4):
                    key = f'{stamp}-p{number}'
                    self.tables['purchases'].append({
                        'id': key, 'purchase_date': stamp + '-02', 'purchase_kind': 'first' if number < 2 else 'renewal',
                        'total_sessions': 2, 'total_amount': 2100, 'total_net_amount': 2000,
                        'calculation_rule_version': 'historical-alignment-v3'})
                    for sequence in (1, 2):
                        self.tables['session_usages'].append({'id': key + f'-u{sequence}', 'purchase_id': key,
                            'usage_date': stamp + f'-{10 + sequence:02d}', 'created_at': '', 'deducted_net_amount': 1000})
                for number in range(month % 3 + 3):
                    self.tables['trial_items'].append({'id': f'{stamp}-t{number}', 'entry_date': stamp + '-05',
                                                       'amount': 0 if number == 0 else 800})
    def table(self, name):
        return DemoQuery(self.tables[name])
    def rpc(self, name, params):
        from collections import Counter
        from operations_metrics import completion_dates
        if name != 'operations_completed_counts':
            raise ValueError('不支援的虛構查詢')
        end = params['p_end']
        completed = completion_dates(
            [row for row in self.tables['purchases'] if row['purchase_date'] <= end],
            [row for row in self.tables['session_usages'] if row['usage_date'] <= end], [])
        counts = Counter(value for value in completed.values() if params['p_start'] <= str(value) <= end)
        return DemoQuery([{'completed_date': str(key), 'completed_courses': value} for key, value in sorted(counts.items())])


st.set_page_config(page_title='營運管理本機測試 v1.13.42', layout='wide')
st.warning('本機測試 v1.13.42｜全部為虛構資料，不連線正式系統。')
role_label = st.sidebar.selectbox('測試角色', ['系統管理員', '主管', '教練'])
role = {'系統管理員': 'admin', '主管': 'manager', '教練': 'coach'}[role_label]
today = datetime.now(ZoneInfo('Asia/Taipei')).date()
render_operations_overview({'id': 'demo-only', 'role': role}, lambda: DemoClient(today.year), today)
