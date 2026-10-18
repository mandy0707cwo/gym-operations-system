from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from financial_reconciliation import allocate_payments,course_ledger,project_ledger
from financial_calculations import FinancialDataError


def sample():
    return {'purchases':[{'id':'p','purchase_code':'TEST-001','total_amount':'20280','total_sessions':12}],
            'payments':[{'id':'pay','purchase_id':'p','amount':'20280','paid_date':'2026-01-01','created_at':'2026-01-01T00:00:00Z'}],
            'usages':[{'id':'u'+str(i),'purchase_id':'p','session_seq':i+1,'usage_date':'2026-02-01','deducted_amount':'1690','deducted_net_amount':'1610' if i<4 else '1609'} for i in range(7)],
            'terminations':[{'id':'t','purchase_id':'p','termination_date':'2026-08-25','termination_type':'expired','recognized_amount':'8450','fee_amount':'0','refund_amount':'0'}],
            'projects':[],'entries':[],'deposits':[]}


class ReconciliationTests(unittest.TestCase):
    def test_expiry_uses_paid_net_less_saved_usage_not_gross_conversion(self):
        r=course_ledger(sample())[0]
        self.assertEqual(r['old_ledger_net'],-1)
        self.assertEqual(r['standardized_net'],0)
        self.assertEqual(r['difference'],1)
        self.assertEqual(r['termination']['new_net'],8047)

    def test_refund_absorbs_net_tail(self):
        data=sample();data['terminations'][0].update(termination_type='refund',fee_amount='1690',refund_amount='6760')
        r=course_ledger(data)[0]['termination']
        self.assertEqual(r['fee_net'],1610)
        self.assertEqual(r['refund_net'],6437)
        self.assertEqual(r['fee_net']+r['refund_net'],8047)

    def test_payment_tail_and_overpayment_are_not_capped(self):
        p=[{'id':'p','total_amount':'100'}]
        pays=[{'id':str(i),'purchase_id':'p','paid_date':'2026-01-01','amount':x} for i,x in enumerate(['30','30','40','5'])]
        r=allocate_payments(p,pays)
        self.assertEqual([x['net_reconstructed'] for x in r],[29,29,37,5])
        self.assertEqual(sum(x['net_reconstructed'] for x in r),100)

    def test_orphan_duplicate_and_missing_payment_fail(self):
        for field,value in [('purchase_id','missing'),('amount',None),('amount','-1')]:
            data=sample();data['payments'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(FinancialDataError):allocate_payments(data['purchases'],data['payments'])

    def test_project_sums_events_instead_of_reconverting_balance(self):
        data={'projects':[{'id':'p','funding_type':'stored'}],
              'deposits':[{'id':'d','project_id':'p','amount':'100','transaction_type':'opening'}],
              'entries':[{'id':'x'+str(i),'project_id':'p','line_amount':'10.01'} for i in range(3)]}
        result=project_ledger(data)[0]
        self.assertEqual(result['standardized_net_balance'],65)
        self.assertEqual(result['old_net_balance'],67)
        self.assertTrue(result['opening_provenance_pending'])

    def test_post_termination_usage_blocks_adjustment(self):
        data=sample();data['usages'][0]['usage_date']='2026-09-01'
        with self.assertRaises(FinancialDataError):course_ledger(data)

    def test_source_data_unchanged(self):
        data=sample();before=deepcopy(data);course_ledger(data)
        self.assertEqual(data,before)
