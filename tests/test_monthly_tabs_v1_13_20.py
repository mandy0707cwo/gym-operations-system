"""執行實際每月查詢函式；僅虛構資料，不連正式資料庫。"""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from test_confirmed_queries import SCRIPT

ROOT=Path(__file__).resolve().parents[1]
TABS=['每月報表','體驗項目','單次銷售','教練查詢']


class MonthlyTabRemovalTests(unittest.TestCase):
    def app(self, role='admin', selected=None):
        app=AppTest.from_string('APP_PATH='+repr(str(ROOT/'app.py'))+'\n'+SCRIPT,default_timeout=30)
        app.session_state['view']='financial'
        app.session_state['role']=role
        if selected is not None:
            app.session_state['financial_report_view']=selected
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_default_exact_tabs_and_no_transaction_reads(self):
        app=self.app()
        self.assertEqual([t.label for t in app.tabs],TABS)
        self.assertEqual(app.session_state['financial_report_view'],'每月報表')
        self.assertEqual(app.session_state['reads'],[])
        self.assertFalse(app.dataframe)

    def test_all_removed_and_invalid_states_recover_before_widget(self):
        for stale in ['會員報表','其他報表','課程中止','不存在的分頁','',123]:
            with self.subTest(stale=stale):
                app=self.app(selected=stale)
                self.assertEqual(app.session_state['financial_report_view'],'每月報表')
                self.assertEqual([t.label for t in app.tabs],TABS)
                self.assertEqual(app.session_state['reads'],[])
                self.assertFalse(app.dataframe)
                self.assertEqual(len(app.get('download_button')),0)

    def test_each_retained_tab_stays_selected_and_waits_for_query(self):
        for selected in TABS:
            with self.subTest(selected=selected):
                app=self.app(selected=selected)
                self.assertEqual(app.session_state['financial_report_view'],selected)
                # AppTest 會將日期區間／截止日期子分頁攤平，僅比對此層入口。
                self.assertEqual([t.label for t in app.tabs if t.label not in ('日期區間','截止日期')],TABS)
                self.assertFalse(app.dataframe)
                self.assertEqual(app.session_state['reads'],[])

    def test_retired_state_does_not_return_on_second_rerun(self):
        app=self.app(selected='其他報表')
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['financial_report_view'],'每月報表')
        self.assertEqual(app.session_state['reads'],[])

    def test_non_admin_roles_cannot_reach_tabs_or_read_tables(self):
        for role in ['coach','shared_coach','manager','unknown']:
            with self.subTest(role=role):
                app=self.app(role=role,selected='會員報表')
                self.assertFalse(app.tabs)
                self.assertEqual(app.session_state['reads'],[])
                self.assertEqual(len(app.warning),1)


if __name__=='__main__':
    unittest.main()
