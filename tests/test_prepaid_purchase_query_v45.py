"""預收購買_ID篩選只用虛構資料；核對各期、尾差及下載。"""
from copy import deepcopy
from io import BytesIO
import unittest
from openpyxl import load_workbook
import test_online_finance as base


def fixture():
    data=base.tables(); p=data['purchases'][0]
    data['members'].append({'id':'m2','member_name':'虛構另一會員'})
    data['purchases']=[dict(p,payment_plan='installment',installment_count=3),
        dict(p,id='p2',purchase_code='20260902-001',purchase_date='2026-09-02',payment_plan='installment',installment_count=3),
        dict(p,id='p3',purchase_code='20260903-001',purchase_date='2026-09-03',member_id='m2',total_amount=1050)]
    data['purchase_payments']=[
        {'id':'a3','purchase_id':'p1','paid_date':'2026-09-20','amount':700,'net_amount':666,'installment_no':3,'payment_kind':'supplement'},
        {'id':'b2','purchase_id':'p2','paid_date':'2026-09-10','amount':700,'net_amount':667,'installment_no':2},
        {'id':'c1','purchase_id':'p3','paid_date':'2026-09-03','amount':1050,'net_amount':1000,'installment_no':1},
        {'id':'a1','purchase_id':'p1','paid_date':'2026-09-01','amount':700,'net_amount':667,'installment_no':1},
        {'id':'b1','purchase_id':'p2','paid_date':'2026-09-02','amount':700,'net_amount':667,'installment_no':1},
        {'id':'a2','purchase_id':'p1','paid_date':'2026-09-05','amount':700,'net_amount':667,'installment_no':2}]
    return data


class PrepaidPurchaseTests(unittest.TestCase):
    app=base.FinancialScreenTests.app

    def open(self,**state):
        return self.app('general',tables=fixture(),general_query_main_tab='預收款項',
                        general_prepaid_mode='會員查詢',**state)

    def search(self,app,purchase='',member='',status='全部'):
        app.text_input(key='gpi_purchase_id').set_value(purchase)
        app.text_input(key='gpi_member').set_value(member)
        app.selectbox(key='gpi_status').set_value(status)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        return app

    def test_field_present_and_no_transactions_before_query(self):
        app=self.open()
        self.assertEqual(app.text_input(key='gpi_purchase_id').label,'購買_ID')
        self.assertEqual(len(app.dataframe),0)
        self.assertLessEqual(set(app.session_state['reads']),{'profiles'})
        self.assertNotIn('exports',app.session_state)

    def test_exact_code_spaces_all_periods_tail_and_download_match(self):
        app=self.search(self.open(),purchase=' 20260901-001 ')
        frame=app.dataframe[0].value
        self.assertEqual(frame['購買_ID'].tolist(),['20260901-001']*3)
        self.assertEqual(frame['成交／預收日期'].tolist(),['2026-09-01','2026-09-05','2026-09-20'])
        self.assertEqual(frame['預收金額（含稅）'].sum(),2100)
        self.assertEqual(frame['預收金額（未稅）'].tolist(),[667,667,666])
        self.assertEqual(frame['分期狀態'].tolist(),['付清']*3)
        self.assertEqual(frame['付款期次'].tolist(),['第 1/3 期','第 2/3 期','補繳款'])
        self.assertTrue(frame.equals(app.session_state['exports']['預收款項']))
        book=load_workbook(BytesIO(app.session_state['export_bytes']),data_only=True)
        sheet=book['預收款項']; headers=[cell.value for cell in sheet[1]]
        self.assertEqual([sheet.cell(i,headers.index('購買_ID')+1).value for i in range(2,5)],['20260901-001']*3)
        self.assertEqual(sum(sheet.cell(i,headers.index('預收金額（未稅）')+1).value for i in range(2,5)),2000)

    def test_partial_code_and_uuid_case_insensitive(self):
        app=self.search(self.open(),purchase='202609')
        self.assertEqual(len(app.dataframe[0].value),6)
        app=self.search(app,purchase=' P2 ')
        self.assertEqual(app.dataframe[0].value['購買_ID'].tolist(),['20260902-001']*2)
        self.assertEqual(app.dataframe[0].value['預收金額（未稅）'].sum(),1334)

    def test_member_purchase_and_status_are_intersection(self):
        app=self.search(self.open(),purchase='20260902',member='虛構會員',status='未付清')
        self.assertEqual(len(app.dataframe[0].value),2)
        app=self.search(app,purchase='20260902',member='虛構會員',status='付清')
        self.assertEqual(len(app.dataframe),0)
        self.assertEqual([item.value for item in app.metric],['$ 0','$ 0'])
        app=self.search(app,purchase='20260901',member='另一會員')
        self.assertEqual(len(app.dataframe),0)

    def test_missing_purchase_zero_results_and_no_old_download(self):
        app=self.search(self.open(),purchase='20260901-001')
        self.assertEqual(len(app.get('download_button')),1)
        app=self.search(app,purchase='不存在-999')
        self.assertEqual(len(app.dataframe),0)
        self.assertEqual(len(app.get('download_button')),0)
        self.assertEqual([item.value for item in app.metric],['$ 0','$ 0'])
        self.assertTrue(any('查無' in item.value for item in app.info))

    def test_blank_keeps_original_receipts_and_member_search(self):
        app=self.search(self.open(),purchase='   ')
        self.assertEqual(len(app.dataframe[0].value),6)
        self.assertEqual(app.dataframe[0].value['預收金額（未稅）'].sum(),4334)
        app=self.search(app,member='另一會員')
        self.assertEqual(app.dataframe[0].value['購買_ID'].tolist(),['20260903-001'])

    def test_purchase_criteria_changes_snapshot_and_rerun_reuses_private_data(self):
        app=self.search(self.open(),purchase='20260901')
        count=len(app.session_state['reads']); app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['reads'][count:],['profiles'])
        app.text_input(key='gpi_purchase_id').set_value('20260902').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe),0)
        self.assertEqual(len(app.get('download_button')),0)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value['購買_ID'].tolist(),['20260902-001']*2)
        self.assertEqual(app.session_state['exports']['預收款項']['購買_ID'].tolist(),['20260902-001']*2)

    def test_unauthorized_role_has_no_query_or_export(self):
        app=self.open(role='coach')
        self.assertEqual(len(app.button),0)
        self.assertEqual(len(app.text_input),0)
        self.assertEqual(app.session_state['reads'],[])


if __name__=='__main__': unittest.main()
