"""財務排序只用虛構明細，驗證畫面、Excel及合計，不連線正式資料。"""
from copy import deepcopy
from datetime import date, datetime
from io import BytesIO
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal
from openpyxl import load_workbook
from finance_report_order import DATE_COLUMNS, report_frame, sort_report_dates
from monthly_operation_queries import operation_report_frame
import test_online_finance as base
import test_finance_report_columns_v38 as bonus
from test_financial_backup import load_functions


class PureOrderTests(unittest.TestCase):
    def test_old_to_new_stable_negative_and_unchanged_types(self):
        frame=pd.DataFrame({'日期':['2026-10-01','2025-12-31','2026-10-01','2026-01-01'],
                            '筆次':['a','b','c','d'],'含稅':[105,-210,315,420], '未稅':[100,-200,300,400]})
        before=frame.copy(deep=True); result=sort_report_dates(frame)
        assert_frame_equal(result,frame.iloc[[1,3,0,2]].reset_index(drop=True))
        assert_frame_equal(frame,before)
        self.assertEqual(result['未稅'].sum(),600)
        self.assertEqual(result['含稅'].sum(),630)

    def test_blanks_totals_stay_last_without_dropping_rows(self):
        frame=pd.DataFrame({'日期':['合計',None,'2026-01-02','2026-01-01','',pd.NaT], '金額':[3,0,2,1,0,0]})
        result=sort_report_dates(frame)
        self.assertEqual(result.index.tolist(),list(range(6)))
        assert_frame_equal(result,frame.iloc[[3,2,0,1,4,5]].reset_index(drop=True))

    def test_date_objects_and_datetimes_work_without_conversion(self):
        frame=pd.DataFrame({'日期':pd.Series([date(2026,1,2),datetime(2026,1,1,12),date(2026,1,1)],dtype=object),
                            '筆次':[0,1,2]})
        assert_frame_equal(sort_report_dates(frame),frame.iloc[[1,2,0]].reset_index(drop=True))

    def test_all_declared_dates_and_primary_not_actual_or_expiry(self):
        for column in DATE_COLUMNS:
            result=report_frame({column:['2026-12-31','2026-01-01'],'金額':[2,1]})
            self.assertEqual(result['金額'].tolist(),[1,2],column)
        frame=pd.DataFrame({'銷課日期':['2026-02-01','2026-01-01'],
                            '實際銷課日期':['2025-12-01','2025-12-31'],'有效期限':['2026-03-01','2026-12-31']})
        self.assertEqual(sort_report_dates(frame)['銷課日期'].tolist(),['2026-01-01','2026-02-01'])

    def test_invalid_dates_raise_not_silently_discarded(self):
        for value in ('不是日期','2026-02-30','01/02/2026',123):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'無效日期'):
                report_frame({'日期':['2026-01-01',value]})

    def test_no_date_summary_and_empty_are_unchanged(self):
        for frame in (pd.DataFrame({'帳號':['smc001','smc002'],'金額':[2,1]}),
                      pd.DataFrame(columns=['日期','金額'])):
            assert_frame_equal(sort_report_dates(frame),frame)

    def test_operation_trial_and_single_are_sorted_without_value_changes(self):
        rows=[{'id':str(i),'entry_date':when,'amount':105,'net_amount':100,
               'calculation_rule_version':'historical-alignment-v3','hours':0.5,'coach_id':'c1'}
              for i,when in enumerate(['2026-10-02','2026-09-30','2026-10-01'])]
        original=deepcopy(rows)
        for name in ('體驗項目','單次銷售'):
            frame=operation_report_frame(rows,name,{'c1':'虛構教練'})
            self.assertEqual([str(value) for value in frame['日期']],['2026-09-30','2026-10-01','2026-10-02'])
            self.assertEqual(frame['金額（未稅）'].sum(),300)
            self.assertEqual(frame['時數'].sum(),1.5)
        self.assertEqual(rows,original)


class ScreenOrderTests(unittest.TestCase):
    app=base.FinancialScreenTests.app

    def query(self,app):
        for index,when in enumerate((date(2026,9,1),date(2026,9,30))):
            if len(app.date_input)>index:
                app.date_input[index].set_value(when)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        return app

    def assert_exports_match(self,app):
        for name,frame in app.session_state['exports'].items():
            if frame.empty or not any(column in frame.columns for column in DATE_COLUMNS): continue
            self.assertTrue(any(frame.equals(item.value) for item in app.dataframe),name)
        book=load_workbook(BytesIO(app.session_state['export_bytes']),data_only=True)
        for name,frame in app.session_state['exports'].items():
            if frame.empty or '日期' not in frame.columns: continue
            column=frame.columns.tolist().index('日期')+1
            values=[book[name].cell(i,column).value for i in range(2,len(frame)+2)]
            actual=[str(value)[:10] for value in values]
            self.assertEqual(actual,[str(value)[:10] for value in frame['日期']],name)

    def test_general_usage_sorted_primary_date_screen_and_excel(self):
        data=base.tables(); u=data['session_usages'][0]
        data['session_usages']=[dict(u,id='u'+str(i),usage_date=when,session_seq=i+1,
                                actual_usage_date='2026-08-01',deducted_net_amount=net)
                               for i,(when,net) in enumerate([('2026-09-20',666),('2026-09-02',667),('2026-09-10',667)])]
        app=self.query(self.app('general',tables=data,general_query_main_tab='銷課查詢',general_usage_mode='日期區間'))
        self.assertEqual(app.dataframe[0].value['日期'].tolist(),['2026-09-02','2026-09-10','2026-09-20'])
        self.assertEqual(app.dataframe[0].value['銷課金額（未稅）'].sum(),2000)
        self.assert_exports_match(app)

    def test_general_receipts_sorted_and_tail_allocation_unchanged(self):
        data=base.tables(); p=data['purchase_payments'][0]
        data['purchase_payments']=[dict(p,id='p'+str(i),paid_date=when,amount=700,net_amount=net,installment_no=i+1)
            for i,(when,net) in enumerate([('2026-09-20',666),('2026-09-02',667),('2026-09-10',667)])]
        app=self.query(self.app('general',tables=data,general_query_main_tab='預收款項',general_prepaid_mode='日期區間'))
        frame=app.dataframe[0].value
        self.assertEqual(frame['成交／預收日期'].tolist(),['2026-09-02','2026-09-10','2026-09-20'])
        self.assertEqual(frame['預收金額（未稅）'].tolist(),[667,667,666])
        self.assert_exports_match(app)

    def test_general_purchases_screen_and_excel_ascending(self):
        data=bonus.FinanceReportColumnsTests().bonus_data()
        data['purchases'].reverse()
        app=self.query(self.app('general',tables=data,general_query_main_tab='成交總表',general_purchase_mode='日期區間'))
        frame=app.dataframe[0].value
        self.assertEqual(frame['成交日期'].tolist(),['2026-09-01','2026-09-12','2026-09-15'])
        self.assertEqual(frame['成交金額（含稅）'].sum(),6300)
        self.assert_exports_match(app)

    def test_monthly_bonus_all_dated_exports_and_backup_order(self):
        fixture=bonus.FinanceReportColumnsTests();data=fixture.bonus_data()
        data['purchases'].reverse();data['session_usages'].reverse()
        data['bonus_rules'][0]['effective_from']='2026-10-01'
        app=fixture.monthly(data); frames=app.session_state['exports']
        for name,column in [('每月銷課','日期'),('每月教練談單獎金','成交日期'),
                            ('每月教練結單獎金','課程完成日期'),('談單待確認','日期'),('結單待確認','日期')]:
            values=frames[name][column].tolist()
            self.assertEqual(values,sorted(values),name)
        self.assert_exports_match(app)
        backup=load_functions()['_financial_backup_frames'](data)
        assert_frame_equal(backup['財務-談單待確認'],frames['談單待確認'])
        for name,column in [('財務-銷課明細','銷課日期'),('財務-教練談單獎金','成交日期'),('財務-教練結單獎金','課程完成日期')]:
            values=backup[name][column].tolist()
            self.assertEqual(values,sorted(values),name)

    def test_monthly_operation_screen_download_and_no_initial_transactions(self):
        for name,table in [('體驗項目','trial_items'),('單次銷售','single_sales')]:
            data=base.tables();row=data[table][0]
            data[table]=[dict(row,id=str(i),entry_date=when) for i,when in enumerate(['2026-09-20','2026-09-01'])]
            app=self.app('financial',tables=data,financial_report_view=name)
            self.assertEqual(len(app.dataframe),0)
            app=self.query(app)
            self.assertEqual([str(value) for value in app.dataframe[0].value['日期']],['2026-09-01','2026-09-20'])
            self.assertTrue(app.session_state['exports'][name].equals(app.dataframe[0].value))

    def test_finance_coach_execution_sorted_total_footer_last_but_coach_unchanged(self):
        data=base.tables();row=data['session_usages'][0]
        data['session_usages']=[dict(row,id=str(i),usage_date=when) for i,when in enumerate(['2026-09-20','2026-09-01'])]
        app=self.query(self.app('financial',tables=data,financial_report_view='教練查詢',
                               coach_query_view_export='執行時數'))
        frame=app.session_state['exports']['執行時數_銷課']
        self.assertEqual(frame['日期'].tolist(),['2026-09-01','2026-09-20','合計'])
        self.assertEqual(frame.iloc[-1]['銷課金額'],1400)
        self.assertTrue(app.dataframe[0].value.equals(frame))
        for key in ('執行時數_每日營運',):
            dates=app.session_state['exports'][key]['日期'].tolist()
            self.assertEqual(dates,sorted(dates))
        coach=self.query(self.app('coach',tables=data,coach_query_view_usage='執行時數'))
        self.assertEqual(coach.dataframe[0].value['日期'].tolist(),['2026-09-20','2026-09-01','合計'])

    def test_finance_coach_usage_history_ascending_and_values_preserved(self):
        data=base.tables();row=data['session_usages'][0]
        data['session_usages']=[dict(row,id=str(i),usage_date=when,session_seq=i+1)
            for i,when in enumerate(['2026-09-20','2026-09-01'])]
        p=data['purchases'][0]
        data['purchase_balances']=[{'purchase_id':p['id'],'coach_id':'c1','purchase_date':p['purchase_date'],
            'member_id':'m1','member_name':'虛構會員','course_name':p['course_name'],'total_sessions':3,
            'used_sessions':2,'remaining_sessions':1,'remaining_amount':700,'total_amount':2100,
            'expiry_date':p['expiry_date'],'status':'active','coach_name':'虛構教練'}]
        app=self.app('financial',tables=data,financial_report_view='教練查詢',coach_query_view_export='銷課明細查詢')
        app.button[0].click().run();self.assertFalse(app.exception)
        frame=app.dataframe[0].value
        self.assertEqual(frame['銷課日期'].tolist(),['2026-09-01','2026-09-20'])
        self.assertEqual(frame['銷課金額（未稅）'].sum(),1334)
        self.assertTrue(frame.equals(app.session_state['exports']['銷課明細查詢']))

    def test_finance_coach_overview_sorts_only_visible_date_expiry(self):
        data=base.tables();p=data['purchases'][0]
        data['purchase_balances']=[{'purchase_id':p['id'],'coach_id':'c1','member_name':'虛構會員',
            'course_name':p['course_name'],'total_sessions':3,'used_sessions':1,'remaining_sessions':2,
            'total_amount':2100,'expiry_date':'2027-09-01','status':'active','coach_name':'虛構教練'},
            {'purchase_id':'p2','coach_id':'c1','member_name':'虛構會員乙','course_name':p['course_name'],
             'total_sessions':3,'used_sessions':0,'remaining_sessions':3,'total_amount':2100,
             'expiry_date':'2027-01-01','status':'active','coach_name':'虛構教練'}]
        data['purchases'].append(dict(p,id='p2',purchase_code='20260902-001',purchase_date='2026-09-02'))
        app=self.app('financial',tables=data,financial_report_view='教練查詢',coach_query_view_export='會員課程查詢')
        app.button[0].click().run();self.assertFalse(app.exception)
        frame=app.dataframe[0].value
        self.assertEqual([str(value) for value in frame['效期']],['2027-01-01','2027-09-01'])
        self.assertTrue(frame.equals(app.session_state['exports']['會員課程查詢']))


if __name__=='__main__':
    unittest.main()
