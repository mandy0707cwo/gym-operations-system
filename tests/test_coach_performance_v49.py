from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from coach_performance import CoachPerformance, hours_changes, minutes_from_hours
from coach_performance_ui import performance_chart
from coach_performance_repository import fetch_report, save_hours

START, END = date(2026, 10, 1), date(2026, 10, 31)


def payload(start=START, end=END):
    return {'schema_version': 49, 'start': str(start), 'end': str(end),
            'coaches': [{'id': 'c2', 'username': 'smc002', 'display_name': '虛構乙'}, {'id': 'c1', 'username': 'smc001', 'display_name': '虛構甲'}],
            'facts': [{'coach_id': 'c1', 'day': '2026-10-10', 'metric': k, 'value': v} for k, v in {
                'sales_net': 50000, 'sales_sessions': 40, 'first_orders': 3, 'renewal_orders': 2,
                'usage_net': 10000, 'usage_sessions': 12, 'usage_hours': 60, 'trial_visits': 4, 'paid_trial_visits': 2,
                'trial_hours': 1, 'single_hours': 2, 'project_hours': 1, 'oneoff_net': 3000,
                'completed_courses': 1, 'cancelled_sessions': 4, 'refund_courses': 2, 'refund_net': 8000}.items()],
            'hours': [{'coach_id': 'c1', 'month': '2026-10-01', 'minutes': 9600, 'revision': 1}],
            'cohorts': [{'coach_id': 'c1', 'start_date': str(start), 'end_date': str(end), 'opening_members': 4, 'retained_members': 3}]}


class CalculationTests(unittest.TestCase):
    def test_confirmed_formula_and_no_amount_added_to_hours(self):
        p = payload(); original = deepcopy(p)
        engine = CoachPerformance(p, START, END)
        r = engine.totals('c1')
        self.assertEqual(r['execution_hours'], 64)
        self.assertEqual(r['achievement_rate'], Decimal('.5'))
        self.assertEqual(r['average_sale'], 1250)
        self.assertEqual(r['trial_visits'], 4)
        self.assertEqual(r['trial_rate'], Decimal('1.5'))
        self.assertEqual(r['renewal_rate'], 2)
        self.assertEqual(r['cancellation_rate'], Decimal('.25'))
        self.assertEqual(r['retention_rate'], Decimal('.75'))
        self.assertEqual(r['refund_courses'], 2)
        self.assertEqual(r['oneoff_net'], 3000)
        self.assertEqual(p, original)
        self.assertEqual([c['id'] for c in engine.coaches], ['c1', 'c2'])

    def test_zero_denominator_missing_and_zero_work_hours_are_not_zero_percent(self):
        engine = CoachPerformance(payload(), START, END)
        r = engine.totals('c2')
        for key in ['trial_rate', 'renewal_rate', 'cancellation_rate', 'retention_rate', 'achievement_rate', 'average_sale']:
            self.assertIsNone(r[key])
        self.assertIn('未填工時', r['hours_status'])
        p = payload(); p['hours'][0]['minutes'] = 0
        r = CoachPerformance(p, START, END).totals('c1')
        self.assertIsNone(r['achievement_rate'])
        self.assertEqual(r['work_hours'], 0)
        self.assertIn('為0', r['hours_status'])

    def test_partial_month_and_two_full_months_not_average_rates(self):
        p = payload(); p['end'] = '2026-11-30'
        p['facts'].append({'coach_id': 'c1', 'day': '2026-11-10', 'metric': 'execution_hours', 'value': 999})
        # 未知欄位必須阻擋，不能讓來源擴充悄悄影響合計。
        with self.assertRaises(ValueError):
            CoachPerformance(p, START, date(2026, 11, 30))
        p['facts'][-1]['metric'] = 'usage_hours'; p['facts'][-1]['value'] = 32
        p['hours'].append({'coach_id': 'c1', 'month': '2026-11-01', 'minutes': 4800, 'revision': 1})
        engine = CoachPerformance(p, START, date(2026, 11, 30))
        self.assertEqual(engine.totals('c1')['achievement_rate'], Decimal('.5'))
        self.assertEqual(len(engine.monthly('c1')), 2)
        partial = engine.totals('c1', date(2026, 10, 2), END)
        self.assertIsNone(partial['achievement_rate'])
        self.assertIn('非完整月份', partial['hours_status'])
        del p['hours'][-1]
        self.assertIsNone(CoachPerformance(p, START, date(2026, 11, 30)).totals('c1')['achievement_rate'])

    def test_reversal_negative_counts_and_refunds_are_preserved(self):
        p = payload()
        for row in p['facts']:
            if row['metric'] in ('refund_net', 'refund_courses'):
                row['value'] = -row['value']
        r = CoachPerformance(p, START, END).totals('c1')
        self.assertEqual((r['refund_courses'], r['refund_net']), (-2, -8000))

    def test_source_errors_fail_closed(self):
        for mutation in [lambda p: p['facts'].append(p['facts'][0]),
                         lambda p: p['facts'][0].update(value=None),
                         lambda p: p['facts'][0].update(value='NaN'),
                         lambda p: p['facts'][0].update(value=-1),
                         lambda p: p['facts'][0].update(value='1.5'),
                         lambda p: p['facts'][0].update(day='2026-09-01'),
                         lambda p: p['hours'].append(p['hours'][0]),
                         lambda p: p['cohorts'][0].update(retained_members=5),
                         lambda p: p.update(schema_version=48)]:
            p = payload(); mutation(p)
            with self.assertRaises(ValueError):
                CoachPerformance(p, START, END)

    def test_manual_hours_blank_zero_precision_optimistic_revision(self):
        p = payload()
        edited = [{'coach_id': 'c1', 'hours': 160.25}, {'coach_id': 'c2', 'hours': None}]
        self.assertEqual(hours_changes(START, p['coaches'], p['hours'], edited), [{'coach_id': 'c1', 'minutes': 9615, 'revision': 1}])
        edited[0]['hours'] = 0
        self.assertEqual(hours_changes(START, p['coaches'], p['hours'], edited)[0]['minutes'], 0)
        edited[0]['hours'] = None
        with self.assertRaises(ValueError):
            hours_changes(START, p['coaches'], p['hours'], edited)
        for value in [-1, '.01', 'NaN', 'Infinity', None]:
            with self.assertRaises(ValueError): minutes_from_hours(value)
        self.assertEqual(minutes_from_hours(160.5), 9630)

    def test_chart_keeps_units_month_order_zero_baseline_and_missing_gaps(self):
        rows = [{'月份': '2026-10', 'achievement_rate': .5}, {'月份': '2026-11', 'achievement_rate': None}]
        spec = performance_chart(rows, '月份', '銷課達成率', 'achievement_rate', 'rate', '虛構教練', True).to_dict()
        self.assertEqual(spec['encoding']['x']['sort'], ['2026-10', '2026-11'])
        self.assertEqual(spec['encoding']['y']['axis']['format'], '.1%')
        self.assertTrue(spec['encoding']['y']['scale']['zero'])
        self.assertIsNone(spec['datasets'][spec['data']['name']][1]['數值'])

    def test_repository_role_guard_before_connection(self):
        for role in ['coach', 'shared_coach', None]:
            with self.assertRaises(PermissionError): fetch_report(None, {'role': role}, START, END)
            with self.assertRaises(PermissionError): save_hours(None, {'role': role}, 'x', START, [])


UI_SCRIPT = '''
from datetime import date
import streamlit as st
from operations_ui import render_operations_overview
from test_coach_performance_v49 import payload
class Client:
 def rpc(self,name,params):
  st.session_state.setdefault('calls',[]).append(name)
  if name=='coach_monthly_work_hours':
   p=payload(); r={'month':params['p_month'],'coaches':p['coaches'],'hours':p['hours'] if params['p_month']=='2026-10-01' else []}
  elif name=='coach_performance_report':
   r=payload(date.fromisoformat(params['p_start']),date.fromisoformat(params['p_end']))
  else: raise ValueError(name)
  return type('Request',(),{'execute':lambda self:type('Result',(),{'data':r})()})()
render_operations_overview({'id':'test-admin','role':st.session_state.get('role','admin')},Client,date(2026,10,31))
'''


class UITests(unittest.TestCase):
    def app(self, **state):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string(UI_SCRIPT, default_timeout=30)
        for k, v in state.items(): app.session_state[k] = v
        app.run(); self.assertFalse(app.exception)
        return app

    def test_default_hidden_tab_does_not_read_performance(self):
        app = self.app()
        self.assertNotIn('calls', app.session_state)
        self.assertEqual(len(app.tabs), 4)

    def test_three_tabs_query_only_on_confirmation(self):
        app = self.app(operations_primary='教練績效')
        self.assertNotIn('calls', app.session_state)
        self.assertEqual(len(app.dataframe), 0)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['calls'].count('coach_performance_report'), 1)
        self.assertEqual(len(app.dataframe), 3)  # 成交、執行、工時檢核
        self.assertIn('退費金額', app.dataframe[0].value.columns)
        self.assertIn('總執行時數', app.dataframe[1].value.columns)
        app.run()
        self.assertEqual(app.session_state['calls'].count('coach_performance_report'), 1)

    def test_comparison_nine_charts_and_individual_month_axis(self):
        app = self.app(operations_primary='教練績效', performance_view='教練對比')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('vega_lite_chart')), 9)
        app = self.app(operations_primary='教練績效', performance_view='個別教練績效')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('vega_lite_chart')), 4)
        for chart in app.get('vega_lite_chart'):
            self.assertEqual(json.loads(chart.proto.spec)['encoding']['x']['field'], '月份')

    def test_unauthorized_cannot_read_or_write(self):
        for role in ['coach', 'shared_coach']:
            app = self.app(role=role, operations_primary='教練績效')
            self.assertEqual(len(app.button), 0)
            self.assertNotIn('calls', app.session_state)

    def demo(self):
        from streamlit.testing.v1 import AppTest
        import coach_performance_ui as ui
        # AppTest尚未提供Expander開關操作；只令此原生區塊預設展開，其他流程不替換。
        original = ui.st.expander
        def expanded_work_hours(label, *args, **kwargs):
            if kwargs.get('key') == 'performance_hours_panel':
                kwargs['expanded'] = True
            return original(label, *args, **kwargs)
        patcher = patch.object(ui.st, 'expander', expanded_work_hours)
        patcher.start()
        self.addCleanup(patcher.stop)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'performance_demo.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertIn('虛構資料', app.warning[0].value)
        next(b for b in app.button if b.label == '載入／重新載入工時').click().run()
        self.assertFalse(app.exception)
        return app

    def test_demo_hours_edit_save_and_reload(self):
        app = self.demo()
        editor = next(k for k in app.session_state.filtered_state if k.startswith('performance_hours_editor:'))
        app.session_state[editor] = {'edited_rows': {0: {'上班時數': 160.5}}, 'added_rows': [], 'deleted_rows': []}
        next(b for b in app.button if b.label == '儲存每月工時').click().run()
        self.assertFalse(app.exception)
        saved = list(app.session_state['demo_hours'].values())
        self.assertEqual((saved[0]['minutes'], saved[0]['revision']), (9630, 1))
        self.assertEqual(len(app.session_state['demo_receipts']), 1)
        self.assertEqual(app.dataframe[0].value.iloc[0]['上班時數'], 160.5)
        self.assertEqual(app.dataframe[0].value.iloc[0]['登錄者'], '虛構系統管理員')

    def test_uncertain_save_retries_original_operation_without_duplicate(self):
        import coach_performance_ui as ui
        app = self.demo()
        editor = next(k for k in app.session_state.filtered_state if k.startswith('performance_hours_editor:'))
        app.session_state[editor] = {'edited_rows': {0: {'上班時數': 160}}, 'added_rows': [], 'deleted_rows': []}
        original = ui.save_hours
        def timeout_after_commit(*args):
            original(*args)
            raise TimeoutError('合成網路中斷')
        with patch.object(ui, 'save_hours', timeout_after_commit):
            next(b for b in app.button if b.label == '儲存每月工時').click().run()
        self.assertFalse(app.exception)
        app.run()
        pending_key = next(k for k in app.session_state.filtered_state if k.endswith(':pending'))
        op = app.session_state[pending_key]['id']
        self.assertEqual(list(app.session_state['demo_hours'].values())[0]['revision'], 1)
        next(b for b in app.button if b.label == '重試同一次工時儲存').click().run()
        self.assertFalse(app.exception)
        self.assertNotIn(pending_key, app.session_state)
        self.assertEqual(list(app.session_state['demo_receipts'])[0][1], op)
        self.assertEqual(list(app.session_state['demo_hours'].values())[0]['revision'], 1)


if __name__ == '__main__':
    unittest.main()
