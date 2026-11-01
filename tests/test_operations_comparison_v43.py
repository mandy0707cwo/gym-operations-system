"""月／年顯示及查詢隔離回歸；只用虛構金額，不連正式資料庫。"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import unittest

from streamlit.testing.v1 import AppTest
from test_operations_management_v40 import SCRIPT, data, purchase, usage


class ComparisonTests(unittest.TestCase):
    def app(self, **state):
        app = AppTest.from_string(SCRIPT, default_timeout=30)
        app.session_state['operations_view'] = '同期對比'
        for key, value in state.items():
            app.session_state[key] = value
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_only_month_year_options_and_no_removed_inputs(self):
        app = self.app()
        self.assertEqual(app.segmented_control[0].options, ['月', '年'])
        self.assertEqual(len(app.date_input), 0)
        self.assertEqual([item.label for item in app.selectbox], ['月份'])
        app.segmented_control[0].set_value('年').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox), 0)
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(app.session_state['connections'], 0)

    def test_month_titles_values_dates_and_formulas(self):
        source = data()
        source['purchases'] = [purchase('now', '2026-10-01', gross=2100, net=2000),
                               purchase('prev', '2026-09-01'),
                               purchase('last', '2025-10-01', gross=4200, net=4000)]
        source['session_usages'] = [usage('u', 'now', '2026-10-01', net=2000)]
        source['trial_items'] = [{'id': 't', 'entry_date': '2026-10-01', 'amount': 800}]
        app = self.app(tables=source)
        app.selectbox(key='operations_month').set_value(10).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual([item.label for item in app.metric],
                         ['本期', '比較上月份', '比較去年同月份'] * 4)
        self.assertEqual([item.value for item in app.metric[:3]], ['$ 2,000', '+100.0%', '-50.0%'])
        self.assertEqual([app.metric[i].value for i in (3, 6, 9)], ['$ 2,000', '1', '1'])
        captions = '\n'.join(item.value for item in app.caption)
        self.assertIn('比較上月份：2026-09-01 ～ 2026-09-30', captions)
        self.assertIn('比較去年同月份：2025-10-01 ～ 2025-10-31', captions)
        self.assertNotIn('自訂', captions)
        self.assertNotIn('｜上期：', captions)

    def test_year_only_two_columns_and_aligned_partial_dates(self):
        source = data()
        source['purchases'] = [purchase('now', '2026-10-01', gross=2100, net=2000),
                               purchase('old', '2025-10-01')]
        app = self.app(tables=source, operations_period_kind='年')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual([item.label for item in app.metric], ['本期', '較去年同期'] * 4)
        self.assertEqual([item.value for item in app.metric[:2]], ['$ 2,000', '+100.0%'])
        captions = '\n'.join(item.value for item in app.caption)
        self.assertIn('本期：2026-01-01 ～ 2026-11-01｜較去年同期：2025-01-01 ～ 2025-11-01', captions)
        self.assertNotIn('上期', captions)
        self.assertNotIn('上月份', captions)

    def test_switch_clears_snapshot_and_never_auto_reads(self):
        app = self.app()
        app.button[0].click().run()
        self.assertEqual(len(app.metric), 12)
        self.assertEqual(app.session_state['connections'], 1)
        app.segmented_control[0].set_value('年').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(app.session_state['connections'], 1)
        app.button[0].click().run()
        self.assertEqual(len(app.metric), 8)
        self.assertEqual(app.session_state['connections'], 2)
        app.segmented_control[0].set_value('月').run()
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(app.session_state['connections'], 2)

    def test_old_removed_choices_reset_without_reusing_results(self):
        for old in ('季', '自訂'):
            with self.subTest(old=old):
                app = self.app(operations_period_kind=old,
                    _confirmed_query_operations_comparison={'identity': ('fake-admin', 'admin', (old,)), 'data': {}})
                self.assertEqual(app.segmented_control[0].value, '月')
                self.assertEqual(len(app.metric), 0)
                self.assertEqual(app.session_state['connections'], 0)
                self.assertFalse(app.exception)

    def test_month_year_zero_baselines_and_unauthorized_role(self):
        for kind in ('月', '年'):
            app = self.app(operations_period_kind=kind)
            app.button[0].click().run()
            self.assertEqual(app.metric[1].value, '無基準')
        app = self.app(role='coach')
        self.assertEqual(len(app.button), 0)
        self.assertEqual(app.session_state['connections'], 0)

    def test_year_does_not_calculate_duplicate_baseline(self):
        # 年的前期與去年同期原為同一區間；畫面只計算並呈現一次。
        from operations_metrics import OperationsMetrics
        original = OperationsMetrics.totals
        calls = []
        def observed(engine, period):
            calls.append(period)
            return original(engine, period)
        app = self.app(operations_period_kind='年')
        with patch.object(OperationsMetrics, 'totals', observed):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(calls), 2)
        self.assertEqual((calls[1].start, calls[1].end), (date(2025, 1, 1), date(2025, 11, 1)))


if __name__ == '__main__':
    unittest.main()
