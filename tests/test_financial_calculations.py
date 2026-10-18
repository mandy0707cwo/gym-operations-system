"""共同計算中心：純函式、邊界與已保存值契約；無正式資料、無DB連線。"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
import ast
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from financial_calculations import (TaxRule, FinancialDataError, calculate_money,
    build_operation_result, ConfirmedGrossWindow, business_date, CONFIRMED_GROSS_WINDOWS)


class CalculationTests(unittest.TestCase):
    def record(self, value, day="2026-09-01", id="a"):
        return {"id": id, "entry_date": day, "amount": value}

    def test_half_up_not_bankers_rounding(self):
        self.assertEqual(calculate_money("10.5", basis_confirmed=True).net, 10)
        self.assertEqual(calculate_money("11.025", basis_confirmed=True).net, 11)
        self.assertEqual(calculate_money("12.075", basis_confirmed=True).net, 12)

    def test_each_record_not_month_total_conversion(self):
        r=build_operation_result([self.record("10.5",id=str(i)) for i in range(3)])
        self.assertEqual(r.net_total,30)
        r=build_operation_result([self.record("10.01",id=str(i)) for i in range(3)])
        self.assertEqual(r.net_total,30)
        self.assertEqual(calculate_money("30.03",basis_confirmed=True).net,29)

    def test_fractional_gross_preserved_and_exact_tax_difference(self):
        m=calculate_money("10.01",basis_confirmed=True)
        self.assertEqual(m.gross,Decimal("10.01"))
        self.assertEqual(m.net,10)
        self.assertEqual(m.tax_difference,Decimal("0.01"))

    def test_negative_value_not_clamped(self):
        m=calculate_money("-11.025",basis_confirmed=True)
        self.assertEqual(m.net,-11)
        self.assertEqual(m.warnings,("negative_amount",))

    def test_zero_is_valid_not_missing(self):
        m=calculate_money(0,basis_confirmed=True)
        self.assertEqual(m.net,0)
        self.assertFalse(m.warnings)

    def test_invalid_amounts_never_become_zero(self):
        for v in [None,"", "  ",True,False,"NaN","Infinity","-Infinity","1,200","bad"]:
            with self.subTest(value=v),self.assertRaises(FinancialDataError):
                calculate_money(v,basis_confirmed=True)

    def test_rule_version_and_factor_validation(self):
        for kwargs in [{"divisor":0},{"divisor":-1},{"divisor":"NaN"},{"version":""},{"quantum":"0.01"}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(FinancialDataError):TaxRule(**kwargs)
        rule=TaxRule(version="explicit-test-rule",divisor=Decimal("1.1"))
        self.assertEqual(calculate_money(110,basis_confirmed=True,rule=rule).net,100)

    def test_stored_net_preserved_without_redivision(self):
        m=calculate_money(1690,stored_net=1609,stored_rule_version="historical-frozen")
        self.assertEqual(m.net,1609)
        self.assertEqual(m.origin,"stored")
        self.assertEqual(m.rule_version,"historical-frozen")

    def test_zero_stored_net_preserved(self):
        self.assertEqual(calculate_money(1,stored_net=0,stored_rule_version="saved").net,0)

    def test_explicit_missing_stored_net_is_error(self):
        for value in [None,"", "NaN", "1.5"]:
            with self.subTest(value=value),self.assertRaises(FinancialDataError):
                calculate_money(10,stored_net=value,stored_rule_version="saved")
        with self.assertRaises(FinancialDataError):calculate_money(10,stored_net=1)

    def test_unknown_basis_does_not_guess_tax(self):
        m=calculate_money(1200)
        self.assertIsNone(m.net)
        self.assertIsNone(m.tax_difference)
        self.assertEqual(m.origin,"unconfirmed")

    def test_evidence_period_boundaries_no_implicit_cutover(self):
        for day,confirmed in [("2026-08-31",False),("2026-09-01",True),("2026-09-30",True),("2026-10-01",False),("2030-01-01",False)]:
            with self.subTest(day=day):
                r=build_operation_result([self.record(105,day)],confirmed_windows=CONFIRMED_GROSS_WINDOWS)
                self.assertEqual(r.unknown_count,0 if confirmed else 1)
                self.assertEqual(r.net_total,100 if confirmed else None)

    def test_explicit_evidence_can_be_supplied_without_mutating_default(self):
        window=ConfirmedGrossWindow(date(2026,10,1),date(2026,10,2),"test-only-approved-evidence")
        self.assertEqual(build_operation_result([self.record(105,"2026-10-01")],confirmed_windows=(window,)).net_total,100)
        self.assertIsNone(build_operation_result([self.record(105,"2026-10-01")],confirmed_windows=CONFIRMED_GROSS_WINDOWS).net_total)

    def test_mixed_period_never_produces_partial_net_total(self):
        r=build_operation_result([self.record(105),self.record(105,"2026-08-31","b")],confirmed_windows=CONFIRMED_GROSS_WINDOWS)
        self.assertEqual(r.gross_total,210)
        self.assertIsNone(r.net_total)
        self.assertEqual(r.unknown_count,1)

    def test_empty_result_has_schema_totals(self):
        r=build_operation_result([])
        self.assertEqual(r.lines,())
        self.assertEqual(r.gross_total,0)
        self.assertEqual(r.net_total,0)

    def test_duplicate_source_id_is_error_not_double_count(self):
        with self.assertRaises(FinancialDataError):build_operation_result([self.record(105),self.record(105)])

    def test_missing_source_id_explicitly_flagged(self):
        self.assertEqual(build_operation_result([self.record(105,id=None)]).missing_id_count,1)

    def test_input_records_not_mutated_and_result_mapping_readonly(self):
        records=[self.record("105.00")];old=deepcopy(records)
        r=build_operation_result(records)
        self.assertEqual(records,old)
        with self.assertRaises(TypeError):r.lines[0].source["amount"]=0

    def test_invalid_dates_fail_before_any_summary(self):
        for day in [None,"", "2026-02-30","2026-9-1","2026-09-01T01:00:00",datetime(2026,9,1)]:
            with self.subTest(day=day),self.assertRaises(FinancialDataError):business_date(day)

    def test_core_contains_no_ui_network_database_or_filesystem_import(self):
        tree=ast.parse((ROOT/'financial_calculations.py').read_text(encoding='utf-8'))
        modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(set(modules)&{"streamlit","supabase","pandas","requests","pathlib"})
        self.assertFalse(any(isinstance(n,ast.Import) for n in ast.walk(tree)))

    def test_global_decimal_precision_does_not_change_money_or_totals(self):
        with localcontext() as ctx:
            ctx.prec=3
            result=build_operation_result([self.record('123456.78',id='a'),self.record('123456.78',id='b')])
            self.assertEqual(result.gross_total,Decimal('246913.56'))
            self.assertEqual(result.net_total,235156)
            self.assertEqual(result.lines[0].money.tax_difference,Decimal('5878.78'))

    def test_text_confirmation_is_not_boolean_authorization(self):
        with self.assertRaises(FinancialDataError):calculate_money(105,basis_confirmed='false')

    def test_user_authorized_all_history_standardization(self):
        records=[self.record(105,day,id=str(i)) for i,day in enumerate(['2024-01-01','2026-08-31','2026-09-30','2026-10-01'])]
        result=build_operation_result(records)
        self.assertEqual(result.net_total,400)
        self.assertEqual(result.unknown_count,0)
        self.assertTrue(all('依正式計算中心規格統一' in line.evidence for line in result.lines))


if __name__=='__main__':unittest.main()
