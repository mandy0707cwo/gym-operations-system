"""專案報表只使用虛構資料，核對日期、類型、餘額、時數與 Excel。"""
import ast
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_queries import execution_report, deposit_report


def tax(value, mode):
    return int((Decimal(str(value)) / Decimal('1.05')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def fixtures():
    project = {'id': 'p', 'project_name': '虛構儲值專案', 'funding_type': 'stored', 'stored_amount': 999999, 'stored_date': '2026-07-01'}
    deposits = [
        {'id': 'd1', 'project_id': 'p', 'deposit_date': '2026-07-01', 'amount': 10500, 'transaction_type': 'opening'},
        {'id': 'd2', 'project_id': 'p', 'deposit_date': '2026-08-01', 'amount': 2100, 'transaction_type': 'deposit'},
        {'id': 'd3', 'project_id': 'p', 'deposit_date': '2026-08-03', 'amount': -1050, 'transaction_type': 'reversal'},
        {'id': 'd4', 'project_id': 'p', 'deposit_date': '2026-09-01', 'amount': 1050, 'transaction_type': 'deposit'},
    ]
    entries = [dict(id=f'e{i}', project_id='p', entry_date=day, line_amount=gross, item_hours='0.5', quantity=2,
                    person_name='虛構使用者', item_name='測試項目', coach_id='c', created_at='2026-10-01')
               for i, (day, gross) in enumerate([('2026-07-30', 1050), ('2026-08-01', 2100), ('2026-08-31', 3150), ('2026-09-01', 4200)])]
    return project, entries, deposits


class ReportTests(unittest.TestCase):
    def report(self, mode='range', **kwargs):
        p, e, d = fixtures()
        return execution_report(p, e, d, {'c': '測試教練'}, tax, mode=mode, end=kwargs.pop('end', '2026-08-31'),
                                start=kwargs.pop('start', '2026-08-01'), **kwargs)

    def test_range_opening_excludes_first_day_and_future(self):
        report = self.report()
        self.assertEqual(report['opening'], 9450)
        self.assertEqual(report['gross'], 5250)
        self.assertEqual(report['net'], 5000)
        self.assertEqual(report['frame']['前期餘額'].count(), 1)

    def test_cutoff_is_cumulative_with_month_opening(self):
        report = self.report('cutoff', start=None)
        self.assertEqual(report['opening'], 9450)
        self.assertEqual(report['gross'], 6300)
        self.assertEqual(len(report['frame']), 3)
        self.assertEqual(report['frame']['教練'].unique().tolist(), ['測試教練'])

    def test_next_month_opening_includes_signed_reversal_and_usage(self):
        self.assertEqual(self.report(end='2026-09-30', start='2026-09-01')['opening'], 5250)

    def test_history_uses_entry_date_not_created_date(self):
        self.assertEqual(self.report()['gross'], 5250)

    def test_hours_multiply_quantity_and_no_unit_string(self):
        self.assertEqual(self.report()['frame']['時數'].tolist(), [1, 1])

    def test_exact_columns_range(self):
        self.assertEqual(self.report()['frame'].columns.tolist(), ['前期餘額', '執行日期', '使用者', '執行項目', '時數', '金額（含稅）', '金額（未稅）'])

    def test_exact_columns_cutoff(self):
        self.assertEqual(self.report('cutoff')['frame'].columns.tolist(), ['專案名稱', '前期餘額', '日期', '教練', '使用者', '項目', '時數', '金額（含稅）', '金額（未稅）'])

    def test_latest_dates_first_and_typed(self):
        self.assertEqual(self.report()['frame']['執行日期'].tolist(), [date(2026, 8, 31), date(2026, 8, 1)])

    def test_midmonth_opening_and_no_double_count(self):
        report = self.report(start='2026-08-15')
        self.assertEqual(report['opening'], 8400)
        self.assertEqual(report['gross'], 3150)

    def test_empty_period_keeps_opening(self):
        report = self.report(start='2026-08-15', end='2026-08-20')
        self.assertTrue(report['frame'].empty)
        self.assertEqual(report['gross'], 0)
        self.assertEqual(report['opening'], 8400)

    def test_filter_excludes_another_project(self):
        p, e, d = fixtures()
        e.append({**e[1], 'id': 'other', 'project_id': 'other'})
        self.assertEqual(execution_report(p, e, d, {}, tax, mode='range', start='2026-08-01', end='2026-08-31')['gross'], 5250)

    def test_unfunded_columns_and_note(self):
        p, e, d = fixtures(); p['funding_type'] = 'unfunded'; e[1]['note'] = '測試備註'
        report = execution_report(p, e, [], {'c': '測試教練'}, tax, mode='unfunded', start='2026-08-01', end='2026-08-31')
        self.assertEqual(report['frame'].columns.tolist(), ['日期', '專案名稱', '教練', '使用者', '項目', '時數', '金額（含稅）', '備註'])
        self.assertIn('測試備註', report['frame']['備註'].tolist())
        self.assertIsNone(report['opening'])

    def test_deposits_signed_and_no_stored_amount_double_count(self):
        p, e, d = fixtures(); report = deposit_report(p, d, tax, '2026-08-31')
        self.assertEqual(report['gross'], 11550)
        self.assertEqual(report['net'], 11000)
        self.assertEqual(report['frame']['類型'].tolist(), ['沖銷', '後續儲值', '期初儲值'])
        self.assertEqual(report['frame'].columns.tolist(), ['日期', '專案', '類型', '金額（含稅）', '金額（未稅）', '備註'])

    def test_missing_or_negative_data_are_errors(self):
        for field, bad in [('line_amount', None), ('item_hours', None), ('quantity', 0), ('line_amount', -1), ('line_amount', 'NaN')]:
            p, e, d = fixtures(); e[1][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                execution_report(p, e, d, {}, tax, mode='range', start='2026-08-01', end='2026-08-31')

    def test_invalid_period_and_funding_rejected(self):
        with self.assertRaises(ValueError): self.report(start='2026-09-01')
        with self.assertRaises(ValueError): self.report('unfunded')

    def test_reversal_positive_is_error(self):
        p, e, d = fixtures(); d[2]['amount'] = 1050
        with self.assertRaises(ValueError): deposit_report(p, d, tax, '2026-08-31')

    def test_raw_inputs_not_modified(self):
        p, e, d = fixtures(); before = deepcopy((p, e, d))
        execution_report(p, e, d, {}, tax, mode='range', start='2026-08-01', end='2026-08-31')
        self.assertEqual((p, e, d), before)

    def test_net_metric_exactly_matches_displayed_lines(self):
        p, e, d = fixtures(); e[1]['line_amount'] = '1690.25'; e[2]['line_amount'] = '1690.25'
        report = execution_report(p, e, d, {}, tax, mode='range', start='2026-08-01', end='2026-08-31')
        self.assertEqual(report['net'], int(report['frame']['金額（未稅）'].sum()))
        self.assertEqual(report['gross'], 3380.5)

    def test_excel_dates_totals_and_summary(self):
        from openpyxl import load_workbook
        tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
        excel = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == '_excel_bytes')
        ns = {'BytesIO': BytesIO, 'pd': pd}
        exec(compile(ast.Module(body=[excel], type_ignores=[]), '<excel>', 'exec'), ns)
        report = self.report()
        payload = ns['_excel_bytes']({'查詢結果': report['frame'], '查詢摘要': pd.DataFrame([{'專案執行總計（未稅）': report['net'], '專案執行總計（含稅）': report['gross']}])}, number_formats={'金額（含稅）': '"$"#,##0.00', '金額（未稅）': '"$"#,##0', '時數': '0.##'})
        wb = load_workbook(BytesIO(payload), data_only=True)
        ws = wb['查詢結果']
        self.assertIsInstance(ws['B2'].value, datetime)
        self.assertEqual(ws['B2'].number_format, 'yyyy-mm-dd')
        self.assertEqual(ws.freeze_panes, 'A2')
        self.assertEqual(ws['F2'].number_format, '"$"#,##0.00')
        self.assertEqual(ws['G2'].number_format, '"$"#,##0')
        self.assertEqual(ws['E2'].number_format, '0.##')
        self.assertEqual(wb['查詢摘要']['A1'].value, '專案執行總計（未稅）')
        self.assertEqual(wb['查詢摘要']['B1'].value, '專案執行總計（含稅）')
        self.assertEqual(sum(ws.cell(i, 7).value for i in (2, 3)), wb['查詢摘要']['A2'].value)
        self.assertIsNone(ws['A3'].value)

    def test_parent_admin_gate_and_dynamic_project_tab(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        page = source[source.index('def general_queries_page'):source.index('def financial_report_page')]
        self.assertLess(page.index('if me["role"]!="admin"'), page.index('render_project_queries(me'))
        self.assertIn('if project_tab.open:', page)
        self.assertIn('on_change="rerun"', page)


if __name__ == '__main__':
    unittest.main()
