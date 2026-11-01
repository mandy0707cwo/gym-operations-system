"""虛構資料測試營運管理；不取得正式帳號、不連線正式資料庫。"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from operations_metrics import (OperationsMetrics, Period, annual_totals, calendar_period,
                                change_rate, comparison_periods, course_net, display_value)
from operations_repository import load_sources, paged


def purchase(key, when='2026-10-01', kind='first', sessions=1, gross=1050, net=1000):
    return {'id': key, 'member_id': 'same-member', 'purchase_date': when, 'purchase_kind': kind,
            'total_sessions': sessions, 'total_amount': gross, 'total_net_amount': net,
            'calculation_rule_version': 'historical-alignment-v3'}


def usage(key, purchase_id, when='2026-10-02', net=1000):
    return {'id': key, 'purchase_id': purchase_id, 'usage_date': when,
            'created_at': when + 'T01:00:00+08:00', 'deducted_net_amount': net}


def data():
    return {'purchases': [], 'session_usages': [], 'trial_items': [], 'course_terminations': []}


OCT = Period(date(2026, 10, 1), date(2026, 10, 31))


class MetricTests(unittest.TestCase):
    def test_paid_denominator_all_visits_and_unrelated_first_orders(self):
        source = data()
        source['purchases'] = [purchase('p1'), purchase('p2'), purchase('p3')]
        source['trial_items'] = [{'id': str(n), 'entry_date': '2026-10-05', 'amount': amount}
                                 for n, amount in enumerate([800, 800, 0, 0])]
        # 同名同項目也不能去重；不查會員配對，首次購買3單／付費體驗2次。
        source['trial_items'] += [{'id': 'old', 'entry_date': '2026-09-30', 'amount': 100}]
        original = deepcopy(source)
        result = OperationsMetrics(source).totals(OCT)
        self.assertEqual((result['trial_visits'], result['paid_trial_visits']), (4, 2))
        self.assertEqual(result['trial_rate'], Decimal('1.5'))
        self.assertEqual(result['sales_net'], 3000)
        self.assertEqual(source, original)

    def test_renewals_count_courses_not_members_and_completion_crosses_month(self):
        source = data()
        source['purchases'] = [purchase('old', '2026-09-01', sessions=2, gross=2100, net=2000), purchase('a', kind='renewal'), purchase('b', kind='renewal')]
        source['session_usages'] = [usage('u1', 'old', '2026-09-30'), usage('u2', 'old'), usage('u3', 'a')]
        result = OperationsMetrics(source).totals(OCT)
        self.assertEqual((result['renewal_orders'], result['completed_courses']), (2, 2))
        self.assertEqual(result['renewal_rate'], 1)
        self.assertEqual(result['usage_sessions'], 2)

    def test_termination_is_not_completion_and_future_reversal_does_not_rewrite_past(self):
        source = data()
        source['purchases'] = [purchase('expired', sessions=2), purchase('refund', sessions=2), purchase('done')]
        source['session_usages'] = [usage('u1', 'expired'), usage('u2', 'refund'), usage('u3', 'done')]
        source['course_terminations'] = [
            {'id': 't1', 'purchase_id': 'expired', 'termination_date': '2026-10-10', 'termination_type': 'expired', 'reversed_at': None},
            {'id': 't2', 'purchase_id': 'refund', 'termination_date': '2026-10-10', 'termination_type': 'refund', 'reversed_at': None},
            {'id': 't3', 'purchase_id': 'done', 'termination_date': '2026-10-01', 'termination_type': 'refund', 'reversed_at': '2026-11-01T00:00:00+08:00'},
        ]
        self.assertEqual(OperationsMetrics(source).totals(OCT)['completed_courses'], 0)
        source['course_terminations'][-1]['reversed_at'] = '2026-10-02T00:00:00+08:00'
        self.assertEqual(OperationsMetrics(source).totals(OCT)['completed_courses'], 1)

    def test_no_division_by_zero_and_no_clamping(self):
        result = OperationsMetrics(data()).totals(OCT)
        self.assertIsNone(result['trial_rate'])
        self.assertIsNone(result['renewal_rate'])
        self.assertIsNone(change_rate(1, 0))
        self.assertIsNone(change_rate(0, 0))
        self.assertEqual(change_rate(0, 100), -1)
        self.assertEqual(display_value(Decimal('1.5'), 'rate'), '150.0%')

    def test_saved_net_and_missing_or_wrong_values_fail_closed(self):
        self.assertEqual(course_net(purchase('p', gross=101, net=96)), 96)
        for field, value in [('total_net_amount', None), ('total_net_amount', 97), ('calculation_rule_version', None)]:
            row = purchase('p', gross=101, net=96)
            row[field] = value
            with self.assertRaises(ValueError):
                course_net(row)
        source = data()
        source['purchases'] = [purchase('p')]
        source['session_usages'] = [usage('u', 'p', net=None)]
        with self.assertRaises(ValueError):
            OperationsMetrics(source).totals(OCT)

    def test_sum_per_transaction_not_group_redivision(self):
        source = data()
        source['purchases'] = [purchase(str(n), gross=10, net=10) for n in range(3)]
        self.assertEqual(OperationsMetrics(source).totals(OCT)['sales_net'], 30)
        self.assertEqual(display_value(1280000, 'money'), '$ 1,280,000')

    def test_duplicates_or_orphan_usage_stop_totals(self):
        source = data()
        source['purchases'] = [purchase('p'), purchase('p')]
        with self.assertRaises(ValueError):
            OperationsMetrics(source)

    def test_missing_trial_amount_and_purchase_kind_fail_not_zero(self):
        source = data()
        source['trial_items'] = [{'id': 'trial', 'entry_date': '2026-10-01', 'amount': None}]
        with self.assertRaises(ValueError):
            OperationsMetrics(source).totals(OCT)
        source = data()
        source['purchases'] = [purchase('p', kind=None)]
        with self.assertRaises(ValueError):
            OperationsMetrics(source)

    def test_completion_not_last_sequence_flag_and_overuse_rejected(self):
        source = data()
        source['purchases'] = [purchase('p', sessions=2, gross=2100, net=2000)]
        source['session_usages'] = [dict(usage('u1', 'p'), session_seq=2)]
        self.assertEqual(OperationsMetrics(source).totals(OCT)['completed_courses'], 0)
        source['session_usages'].extend([usage('u2', 'p'), usage('u3', 'p')])
        with self.assertRaises(ValueError):
            OperationsMetrics(source)

    def test_annual_and_period_totals_reconcile_but_rates_not_averaged(self):
        source = data()
        source['purchases'] = [purchase('a', '2026-09-01'), purchase('b', '2026-10-01')]
        source['trial_items'] = [{'id': 'a', 'entry_date': '2026-09-01', 'amount': 100},
                                 {'id': 'b', 'entry_date': '2026-10-01', 'amount': 100},
                                 {'id': 'c', 'entry_date': '2026-10-01', 'amount': 100}]
        engine = OperationsMetrics(source)
        months = annual_totals(engine, 2026, date(2026, 11, 1))
        full = engine.totals(Period(date(2026, 1, 1), date(2026, 11, 1)))
        self.assertEqual(sum(row['totals']['sales_net'] for row in months if row['totals']), full['sales_net'])
        self.assertEqual(full['trial_rate'], Decimal(2) / 3)
        source = data()
        source['session_usages'] = [usage('u', 'missing')]
        with self.assertRaises(ValueError):
            OperationsMetrics(source)

    def test_annual_month_boundary_future_and_no_mutation(self):
        source = data()
        source['purchases'] = [purchase('a', '2026-09-30'), purchase('b', '2026-10-01')]
        months = annual_totals(OperationsMetrics(source), 2026, date(2026, 11, 1))
        self.assertEqual(months[8]['totals']['sales_net'], 1000)
        self.assertEqual(months[9]['totals']['sales_net'], 1000)
        self.assertEqual(months[10]['totals']['sales_net'], 0)
        self.assertIsNone(months[11]['totals'])
        self.assertEqual(len(months), 12)


class PeriodTests(unittest.TestCase):
    def test_completed_month_and_year_boundary(self):
        periods = comparison_periods('月', calendar_period('月', 2026, 1), date(2026, 11, 1))
        self.assertEqual(periods[1], Period(date(2025, 12, 1), date(2025, 12, 31)))
        self.assertEqual(periods[2], Period(date(2025, 1, 1), date(2025, 1, 31)))

    def test_partial_month_clipped_and_leap_day(self):
        periods = comparison_periods('月', calendar_period('月', 2024, 2), date(2024, 2, 29))
        self.assertEqual(periods[1].end, date(2024, 1, 31))
        self.assertEqual(periods[2].end, date(2023, 2, 28))
        periods = comparison_periods('月', calendar_period('月', 2026, 11), date(2026, 11, 1))
        self.assertEqual(periods[1].end, date(2026, 10, 1))
        self.assertEqual(periods[2].end, date(2025, 11, 1))

    def test_quarter_year_and_custom_inclusive_dates(self):
        periods = comparison_periods('季', calendar_period('季', 2026, quarter=4), date(2026, 11, 1))
        self.assertEqual(periods[1], Period(date(2026, 7, 1), date(2026, 8, 1)))
        periods = comparison_periods('年', calendar_period('年', 2026), date(2026, 11, 1))
        self.assertEqual(periods[1], periods[2])
        periods = comparison_periods('自訂', Period(date(2026, 10, 10), date(2026, 10, 12)), date(2026, 11, 1))
        self.assertEqual(periods[1], Period(date(2026, 10, 7), date(2026, 10, 9)))
        with self.assertRaises(ValueError):
            comparison_periods('月', calendar_period('月', 2027, 1), date(2026, 11, 1))


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.records = deepcopy(client.tables.get(table, []))
    def select(self, *args):
        return self
    def order(self, field):
        self.records.sort(key=lambda row: str(row.get(field, '')))
        return self
    def lte(self, field, value):
        self.records = [row for row in self.records if str(row[field]) <= value]
        return self
    def gte(self, field, value):
        self.records = [row for row in self.records if str(row[field]) >= value]
        return self
    def range(self, start, end):
        self.records = self.records[start:end + 1]
        return self
    def execute(self):
        self.client.reads.append(self.table)
        return type('Result', (), {'data': self.records})()


class FakeClient:
    def __init__(self, tables):
        self.tables, self.reads = tables, []
    def table(self, table):
        return FakeQuery(self, table)
    def rpc(self, name, params):
        from collections import Counter
        from operations_metrics import completion_dates
        if name != 'operations_completed_counts':
            raise ValueError('不支援的假資料RPC')
        self.reads.append('rpc:' + name)
        end = params['p_end']
        completed = completion_dates(
            [row for row in self.tables.get('purchases', []) if row['purchase_date'] <= end],
            [row for row in self.tables.get('session_usages', []) if row['usage_date'] <= end],
            [row for row in self.tables.get('course_terminations', []) if row['termination_date'] <= end])
        counts = Counter(value for value in completed.values() if params['p_start'] <= str(value) <= end)
        records = [{'completed_date': str(key), 'completed_courses': value} for key, value in sorted(counts.items())]
        return type('FakeRPC', (), {'execute': lambda self: type('Response', (), {'data': records})()})()


class RepositoryTests(unittest.TestCase):
    def test_every_page_read_and_history_kept(self):
        client = FakeClient({'trial_items': [{'id': str(n)} for n in range(1003)]})
        self.assertEqual(len(paged(lambda: client.table('trial_items').order('id'))), 1003)
        self.assertEqual(len(client.reads), 2)
        source = data()
        source['purchases'] = [purchase('old', '2026-01-01'), purchase('future', '2027-01-01')]
        source['trial_items'] = [{'id': 'old', 'entry_date': '2026-01-01'}, {'id': 'now', 'entry_date': '2026-10-01'}]
        loaded = load_sources(FakeClient(source), {'role': 'manager'}, OCT.start, OCT.end)
        self.assertEqual([row['id'] for row in loaded['purchases']], ['old'])
        self.assertEqual([row['id'] for row in loaded['trial_items']], ['now'])

    def test_unauthorized_roles_never_read(self):
        for role in ['coach', 'shared_coach', None]:
            client = FakeClient(data())
            with self.assertRaises(PermissionError):
                load_sources(client, {'role': role}, OCT.start, OCT.end)
            self.assertEqual(client.reads, [])


SCRIPT = '''
from datetime import date
import streamlit as st
from operations_ui import render_operations_overview
from test_operations_management_v40 import FakeClient
st.session_state.setdefault('tables', {'purchases': [], 'session_usages': [], 'trial_items': [], 'course_terminations': []})
st.session_state.setdefault('connections', 0)
def connection():
 st.session_state['connections'] += 1
 return FakeClient(st.session_state['tables'])
render_operations_overview({'id': 'fake-admin', 'role': st.session_state.get('role', 'admin')}, connection, date(2026, 11, 1))
'''


class UITests(unittest.TestCase):
    def app(self, **state):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string(SCRIPT, default_timeout=30)
        for key, value in state.items():
            app.session_state[key] = value
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_default_no_reads_annual_query_and_private_snapshot(self):
        source = data()
        source['purchases'] = [purchase('p')]
        app = self.app(tables=source)
        self.assertEqual(app.session_state['connections'], 0)
        self.assertEqual(len(app.dataframe), 0)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        frame = app.dataframe[0].value
        self.assertEqual(frame.shape, (7, 13))
        self.assertEqual(frame.iloc[0]['10月'], '$ 1,000')
        self.assertEqual(frame.iloc[0]['12月'], '—')
        charts = app.get('vega_lite_chart')
        self.assertEqual(len(charts), 2)
        chart = json.loads(charts[0].proto.spec)
        self.assertEqual(chart['encoding']['x']['field'], '月份')
        self.assertEqual(chart['encoding']['y']['axis']['format'], ',.0f')
        self.assertEqual(chart['title'], '2026年每月成交金額（未稅）')
        self.assertEqual(json.loads(charts[1].proto.spec)['title'], '2026年每月銷課金額（未稅）')
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['connections'], 1)

    def test_all_comparison_modes_and_zero_baselines(self):
        app = self.app(operations_view='同期對比')
        self.assertEqual(app.session_state['connections'], 0)
        for kind in ['月', '年']:
            app.segmented_control(key='operations_period_kind').set_value(kind).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.metric), 12 if kind == '月' else 8)
            self.assertEqual(app.metric[1].value, '無基準')
            self.assertTrue(any('本期：' in item.value for item in app.caption))

    def test_separate_charts_keep_distinct_money_series_and_future_blank(self):
        from operations_ui import annual_amount_chart
        months = [{'month': 1, 'totals': {'sales_net': 1234, 'usage_net': 567}},
                  {'month': 2, 'totals': {'sales_net': 2345, 'usage_net': 678}},
                  {'month': 3, 'totals': None}]
        original = deepcopy(months)
        for label, field, expected in [('成交金額', 'sales_net', [1234, 2345]), ('銷課金額', 'usage_net', [567, 678])]:
            spec = annual_amount_chart(months, 2026, label, field).to_dict()
            records = spec['datasets'][spec['data']['name']]
            self.assertEqual([row['金額'] for row in records], expected)
            self.assertEqual([row['月份'] for row in records], ['01月', '02月'])
            self.assertNotIn('color', spec['encoding'])
        self.assertEqual(months, original)

    def test_coach_blocked_and_manager_can_query(self):
        app = self.app(role='coach')
        self.assertEqual(app.session_state['connections'], 0)
        self.assertEqual(len(app.button), 0)
        app = self.app(role='manager')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 1)

    def test_demo_entry_runs_without_real_database(self):
        from streamlit.testing.v1 import AppTest
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root / 'operations_demo.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertIn('虛構資料', app.warning[0].value)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 1)


if __name__ == '__main__':
    unittest.main()
