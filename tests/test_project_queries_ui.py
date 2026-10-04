"""只用假資料驗證按鈕門檻、分頁與下載快照；不啟動正式系統。"""
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest

SCRIPT = '''
import sys
from pathlib import Path
sys.path.insert(0, ROOT)
import json
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
from project_queries import render_project_queries
today = __import__('datetime').date.today().isoformat()
TABLES = {
 'projects': [{'id':'p','project_name':'測試儲值','funding_type':'stored','stored_date':today},
              {'id':'u','project_name':'測試請款','funding_type':'unfunded','stored_date':None}],
 'project_deposits': [{'id':'d','project_id':'p','deposit_date':today,'amount':10500,'transaction_type':'opening'}],
 'project_entries': [{'id':'e','project_id':'p','entry_date':today,'line_amount':1050,'coach_id':'c','person_name':'虛構姓名','item_name':'測試項目','item_hours':0.5,'quantity':2},
                     {'id':'f','project_id':'u','entry_date':today,'line_amount':2100,'coach_id':'c','person_name':'虛構姓名','item_name':'測試請款','item_hours':1,'quantity':3,'note':'請款備註'}],
 'profiles': [{'id':'c','display_name':'測試教練'}],
}
class Query:
 def __init__(self, table):
  st.session_state.setdefault('reads', []).append(table)
  self.records = list(TABLES[table])
 def select(self, *_): return self
 def order(self, *_, **kw): return self
 def eq(self, field, value):
  self.records = [x for x in self.records if x.get(field)==value]; return self
 def in_(self, field, values):
  self.records = [x for x in self.records if x.get(field) in values]; return self
 def lte(self, field, value):
  self.records = [x for x in self.records if str(x.get(field))<=value]; return self
 def gte(self, field, value):
  self.records = [x for x in self.records if str(x.get(field))>=value]; return self
class Client:
 def table(self, table): return Query(table)
def tax(value, mode):
 return int((Decimal(str(value))/Decimal('1.05')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
def excel(frames):
 st.session_state['exported']={k:v.to_dict('records') for k,v in frames.items()}
 return json.dumps(st.session_state['exported'], ensure_ascii=False, default=str).encode('utf-8')
# AppTest尚不支援送回動態tabs的選擇值；在每次模擬rerun前固定選定分頁。
if 'test_mode' in st.session_state:
 st.session_state['project_query_stored_mode'] = st.session_state['test_mode']
if 'test_funding' in st.session_state:
 st.session_state['project_query_funding'] = st.session_state['test_funding']
render_project_queries({'role':st.session_state.get('role','admin')}, Client, lambda build:build().records, tax, excel)
'''


class UITests(unittest.TestCase):
    def app(self):
        root = str(Path(__file__).resolve().parents[1])
        app = AppTest.from_string('ROOT = ' + repr(root) + '\n' + SCRIPT, default_timeout=20).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def submit(self, app, value='p'):
        app.selectbox[0].set_value(value)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)

    def test_initial_load_reads_no_transactions(self):
        app = self.app()
        self.assertEqual(app.session_state['reads'], ['projects'])
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(len(app.get('download_button')), 0)

    def test_range_result_totals_hours_and_download(self):
        app = self.app(); self.submit(app)
        self.assertEqual([m.label for m in app.metric], ['專案執行總計（未稅）', '專案執行總計（含稅）'])
        self.assertEqual(app.metric[0].value, '$ 1,000')
        self.assertEqual(app.dataframe[0].value['時數'].tolist(), [1])
        self.assertEqual(len(app.get('download_button')), 1)
        self.assertEqual(app.session_state['exported']['查詢摘要'][0]['專案執行總計（未稅）'], 1000)

    def test_rerun_preserves_download_without_financial_reads(self):
        app = self.app(); self.submit(app)
        before = app.session_state['reads'].count('project_entries')
        app.run()
        self.assertEqual(app.session_state['reads'].count('project_entries'), before)
        self.assertEqual(len(app.get('download_button')), 1)
        self.assertEqual(len(app.dataframe), 1)

    def test_cutoff_only_runs_when_submitted(self):
        app = self.app(); app.session_state['test_mode'] = '截止日期'; app.run()
        self.assertNotIn('project_entries', app.session_state['reads'])
        self.submit(app)
        self.assertIn('教練', app.dataframe[0].value.columns)
        self.assertEqual(app.dataframe[0].value['教練'].tolist(), ['測試教練'])

    def test_deposit_does_not_read_entries_or_coaches(self):
        app = self.app(); app.session_state['test_mode'] = '累計儲值金額'; app.run(); self.submit(app)
        self.assertNotIn('project_entries', app.session_state['reads'])
        self.assertNotIn('profiles', app.session_state['reads'])
        self.assertEqual(app.metric[0].label, '累計儲值金額（未稅）')
        self.assertEqual(app.metric[0].value, '$ 10,000')

    def test_unfunded_columns_and_only_needed_tables(self):
        app = self.app(); app.session_state['test_funding'] = '未儲值專案'; app.run(); self.submit(app, 'u')
        self.assertNotIn('project_deposits', app.session_state['reads'])
        self.assertEqual(app.dataframe[0].value['備註'].tolist(), ['請款備註'])
        self.assertEqual(app.dataframe[0].value['時數'].tolist(), [3])
        self.assertEqual(len(app.metric), 0)

    def test_blank_project_does_not_query(self):
        app = self.app(); app.button[0].click().run()
        self.assertEqual(len(app.error), 1)
        self.assertNotIn('project_entries', app.session_state['reads'])

    def test_invalid_range_clears_previous_result(self):
        app = self.app(); self.submit(app)
        app.date_input[0].set_value(date(2026, 12, 31)); app.date_input[1].set_value(date(2026, 1, 1))
        app.button[0].click().run()
        self.assertEqual(len(app.error), 1)
        self.assertEqual(len(app.get('download_button')), 0)

    def test_nonadmin_has_no_database_access(self):
        app = self.app(); app.session_state['reads'] = []; app.session_state['role'] = 'coach'; app.run()
        self.assertEqual(app.session_state['reads'], [])
        self.assertEqual(len(app.warning), 1)
        self.assertEqual(len(app.get('download_button')), 0)


if __name__ == '__main__':
    unittest.main()
