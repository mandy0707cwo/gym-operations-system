"""顯示篩選只用合成資料；不連正式資料庫、不變更財務計算。"""
from copy import deepcopy
from datetime import date
import json
import unittest

from coach_performance import CoachPerformance, hours_changes
from coach_performance_ui import coach_label, _hours_entry
from coach_visibility import visible_coaches
import test_coach_performance_v49 as previous

START, END = previous.START, previous.END


def sample(start=START, end=END):
    p = previous.payload(start, end)
    p['coaches'] = [
        {'id': 'c1', 'username': 'smc001', 'display_name': '停用有績效', 'active': False},
        {'id': 'c2', 'username': 'smc002', 'display_name': '停用無資料', 'active': False},
        {'id': 'c3', 'username': 'smc003', 'display_name': '啟用無資料', 'active': True}]
    if start.month != 10:
        p.update(facts=[], cohorts=[], hours=[])
    return p


class PolicyTests(unittest.TestCase):
    def test_disabled_with_evidence_kept_active_zero_kept_disabled_empty_hidden(self):
        p = sample(); original = deepcopy(p)
        engine = CoachPerformance(p, START, END)
        totals = {c['id']: engine.totals(c['id']) for c in engine.coaches}
        self.assertEqual([c['id'] for c in visible_coaches(engine)], ['c1', 'c3'])
        self.assertEqual(coach_label(visible_coaches(engine)[0]), 'smc001 停用有績效（已停用）')
        self.assertEqual(coach_label(visible_coaches(engine)[1]), 'smc003 啟用無資料')
        self.assertEqual(p, original)
        self.assertEqual(totals, {c['id']: engine.totals(c['id']) for c in engine.coaches})

    def test_zero_value_record_free_trial_negative_and_offset_still_evidence(self):
        for field, value in [('trial_visits', 1), ('oneoff_net', 0), ('refund_net', -100), ('refund_courses', 0), ('cancelled_sessions', 1)]:
            p = sample(); p.update(hours=[], cohorts=[])
            p['facts'] = [{'coach_id': 'c1', 'day': '2026-10-15', 'metric': field, 'value': value}]
            self.assertIn('c1', [c['id'] for c in visible_coaches(CoachPerformance(p, START, END))])

    def test_membership_denominator_or_positive_month_hours_keeps_disabled(self):
        p = sample(); p['facts'] = []; p['hours'] = []
        self.assertIn('c1', [c['id'] for c in visible_coaches(CoachPerformance(p, START, END))])
        p['cohorts'] = []; p['hours'] = previous.payload()['hours']
        self.assertIn('c1', [c['id'] for c in visible_coaches(CoachPerformance(p, START, END))])
        p['hours'][0]['minutes'] = 0
        self.assertNotIn('c1', [c['id'] for c in visible_coaches(CoachPerformance(p, START, END))])
        p['hours'][0].update(minutes=60, month='2026-09-01')
        self.assertNotIn('c1', [c['id'] for c in visible_coaches(CoachPerformance(p, START, END))])

    def test_changing_period_does_not_keep_historical_disabled_name(self):
        oct_ids = [c['id'] for c in visible_coaches(CoachPerformance(sample(), START, END))]
        a, b = date(2026, 11, 1), date(2026, 11, 30)
        nov_ids = [c['id'] for c in visible_coaches(CoachPerformance(sample(a, b), a, b))]
        self.assertEqual(oct_ids, ['c1', 'c3']); self.assertEqual(nov_ids, ['c3'])

    def test_invalid_status_refused_not_silently_included(self):
        for value in [None, 'false', 0, 1]:
            p = sample(); p['coaches'][0]['active'] = value
            with self.assertRaises(ValueError): visible_coaches(CoachPerformance(p, START, END))

    def test_monthly_hours_filter_preserves_hidden_saved_records(self):
        p = sample()
        rows = [{'coach_id': 'c2', 'month': str(START), 'minutes': 0, 'revision': 7}]
        data = {'month': str(START), 'coaches': p['coaches'], 'hours': rows}
        original = deepcopy(data)
        entry = _hours_entry(data, p)
        self.assertEqual(entry['visible_ids'], ['c1', 'c3'])
        shown = [c for c in p['coaches'] if c['id'] in entry['visible_ids']]
        changes = hours_changes(START, shown, rows, [{'coach_id': 'c1', 'hours': 160}, {'coach_id': 'c3', 'hours': None}])
        self.assertEqual(changes, [{'coach_id': 'c1', 'minutes': 9600, 'revision': 0}])
        self.assertEqual(data, original)
        self.assertEqual(entry['data']['hours'], rows)


SCRIPT = '''
from datetime import date
from types import SimpleNamespace
import streamlit as st
from coach_performance_ui import render_coach_performance
from test_coach_visibility_v50 import sample
class Client:
 def rpc(self,name,p):
  st.session_state.setdefault('reads',[]).append(name)
  if name=='coach_performance_report':
   data=sample(date.fromisoformat(p['p_start']),date.fromisoformat(p['p_end']))
  elif name=='coach_monthly_work_hours':
   x=sample();data={'month':p['p_month'],'coaches':x['coaches'],'hours':[]}
  else: raise AssertionError('unexpected write '+name)
  return SimpleNamespace(execute=lambda:SimpleNamespace(data=data))
render_coach_performance({'id':st.session_state.get('user','demo-admin'),'role':'admin'},Client,date(2026,11,30))
'''


class UITests(unittest.TestCase):
    def app(self, view='績效總表'):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string(SCRIPT, default_timeout=30)
        app.session_state['performance_view'] = view
        app.run(); self.assertFalse(app.exception)
        return app

    def query(self, app, month=10):
        if app.selectbox:
            next(x for x in app.selectbox if x.label == '月份').set_value(month)
        next(b for b in app.button if b.label == '查詢').click().run()
        self.assertFalse(app.exception)
        return app

    def test_summary_and_selector_use_same_policy_without_initial_reads(self):
        app = self.app()
        self.assertNotIn('reads', app.session_state)
        self.assertEqual(len(app.multiselect), 0)
        self.query(app)
        self.assertEqual(app.multiselect[0].options, ['smc001 停用有績效（已停用）', 'smc003 啟用無資料'])
        for frame in app.dataframe:
            if '教練' in frame.value:
                self.assertEqual(frame.value['教練'].tolist(), app.multiselect[0].options)
        self.assertFalse(app.error)

    def test_coach_filter_is_local_and_month_change_clears_stale_selection(self):
        app = self.query(self.app())
        reads = list(app.session_state['reads'])
        app.multiselect[0].set_value(['c1']).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['reads'], reads)
        self.assertEqual(len(app.dataframe[0].value), 1)
        self.query(app, 11)
        self.assertEqual(app.multiselect[0].value, [])
        self.assertEqual(app.multiselect[0].options, ['smc003 啟用無資料'])
        self.assertEqual(app.dataframe[0].value['教練'].tolist(), ['smc003 啟用無資料'])

    def test_all_nine_comparison_charts_exclude_inactive_empty(self):
        app = self.query(self.app('教練對比'))
        charts = app.get('vega_lite_chart')
        self.assertEqual(len(charts), 9)
        for chart in charts:
            spec = json.loads(chart.proto.spec)
            self.assertEqual(spec['encoding']['x']['sort'], ['smc001 停用有績效（已停用）', 'smc003 啟用無資料'])

    def test_individual_selector_and_four_charts_apply_policy(self):
        app = self.app('個別教練績效')
        app.date_input[0].set_value(START); app.date_input[1].set_value(END)
        next(b for b in app.button if b.label == '查詢').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].options, ['smc001 停用有績效（已停用）', 'smc003 啟用無資料'])
        self.assertEqual(len(app.get('vega_lite_chart')), 4)
        app.date_input[0].set_value(date(2026, 11, 1)); app.date_input[1].set_value(date(2026, 11, 30))
        next(b for b in app.button if b.label == '查詢').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].options, ['smc003 啟用無資料'])
        self.assertEqual(app.selectbox[0].value, 'c3')

    def test_old_snapshot_and_other_account_do_not_reuse_wrong_roster(self):
        app = self.query(self.app())
        app.session_state['user'] = 'another-admin'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.multiselect), 0)
        self.assertFalse(app.dataframe)


if __name__ == '__main__':
    unittest.main()
