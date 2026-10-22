"""只驗證系統既有Excel輸出函式的排班下載，不另交付測試報表。"""
import ast
from datetime import date,datetime
from io import BytesIO
from pathlib import Path
import unittest
import pandas as pd
from openpyxl import load_workbook
from scheduling import export_rows


class ScheduleExportTests(unittest.TestCase):
    def test_saved_rows_only_real_dates_and_no_formulas(self):
        root=Path(__file__).resolve().parents[1]
        node=next(n for n in ast.parse((root/'app.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='_excel_bytes')
        ns={'pd':pd,'BytesIO':BytesIO}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-export>','exec'),ns)
        records=export_rows([{'id':'c','display_name':'=惡意公式'}],[{'coach_id':'c','state':'draft'}],
            [{'coach_id':'c','work_date':'2026-10-04','shift_code':'B','start_time':'12:00:00','end_time':'21:00:00','note':'=1+1'}])
        payload=ns['_excel_bytes']({'排班明細':pd.DataFrame(records)})
        wb=load_workbook(BytesIO(payload));ws=wb['排班明細']
        self.assertIsInstance(ws['A2'].value,(date,datetime))
        self.assertEqual(ws['A2'].number_format,'yyyy-mm-dd')
        self.assertEqual(ws['D2'].value,'12:00')
        self.assertEqual(ws.freeze_panes,'A2');self.assertTrue(ws.auto_filter.ref)
        self.assertEqual(ws.max_row,2)
        self.assertFalse(any(c.data_type=='f' for row in ws for c in row))
        self.assertEqual(len(wb._external_links),0)

    def test_backup_includes_schedule_tables_with_stable_keys(self):
        frames,orders=self.backup()
        for name in ('排班月份','每日排班','排班預設','排班異動','每月排休額度','排休額度異動','其他請假紀錄','請假異動紀錄'):self.assertIn(name,frames)
        self.assertEqual(orders['staff_schedule_allowances'],['month_start','month_start'])
        self.assertEqual(orders['staff_schedule_days'],['coach_id','work_date'])
        self.assertEqual(orders['staff_schedule_months'],['coach_id','month_start'])
        self.assertIn('課程購買',frames);self.assertIn('銷課紀錄',frames)

    def test_backup_read_error_does_not_export_partial_file(self):
        with self.assertRaisesRegex(RuntimeError,'完整備份失敗'):self.backup(fail=True)

    def backup(self,fail=False):
        root=Path(__file__).resolve().parents[1]
        node=next(n for n in ast.parse((root/'app.py').read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='_full_system_backup_bytes')
        orders={}
        class Query:
            def __init__(self,name):self.name=name;orders[name]=[]
            def select(self,*a):return self
            def order(self,key):orders[self.name].append(key);return self
        class API:
            def table(self,name):
                if fail and name=='staff_schedule_days':raise RuntimeError('測試讀取失敗')
                return Query(name)
        ns={'pd':pd,'datetime':datetime,'secret':lambda _:None,'paged_rows':lambda factory:(factory() and []),
            '_financial_backup_frames':lambda data:{},'_excel_bytes':lambda frames:frames}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-backup>','exec'),ns)
        return ns['_full_system_backup_bytes'](API()),orders
