from decimal import Decimal
import unittest
from usage_funds import usage_funds


class UsageFundsTests(unittest.TestCase):
    def funds(self, paid, remaining=8000, sessions=4):
        return usage_funds({'purchase_id':'p','total_amount':10000,'remaining_amount':remaining,
            'total_sessions':5,'remaining_sessions':sessions},[{'purchase_id':'p','amount':paid},
            {'purchase_id':'other','amount':99999}])

    def test_uses_receipts_not_contract_balance(self):
        f=self.funds(3000)
        self.assertEqual(f['actual_prepaid_balance'],1000)
        self.assertEqual(f['next_usage_amount'],2000)
        self.assertEqual(f['usage_shortfall'],1000)

    def test_exact_enough_zero_and_negative(self):
        self.assertEqual(self.funds(4000)['usage_shortfall'],0)
        self.assertEqual(self.funds(2000)['usage_shortfall'],2000)
        self.assertEqual(self.funds(1000)['actual_prepaid_balance'],-1000)

    def test_last_amount_uses_contract_not_receipts(self):
        f=self.funds(9000,remaining=2000,sessions=1)
        self.assertEqual(f['next_usage_amount'],2000)
        self.assertEqual(f['usage_shortfall'],1000)

    def test_half_up_and_one_cent_short(self):
        f=usage_funds({'purchase_id':'p','total_amount':'1.01','remaining_amount':'1.01',
            'total_sessions':2,'remaining_sessions':2},[{'purchase_id':'p','amount':'.50'}])
        self.assertEqual(f['next_usage_amount'],Decimal('.51'))
        self.assertEqual(f['usage_shortfall'],Decimal('.01'))

    def test_missing_invalid_and_empty_payments(self):
        for v in [None,'bad','NaN','Infinity']:
            with self.subTest(v=v), self.assertRaises(ValueError): self.funds(v)
        f=usage_funds({'purchase_id':'p','total_amount':100,'remaining_amount':100,
            'total_sessions':1,'remaining_sessions':1},[])
        self.assertEqual(f['usage_shortfall'],100)
