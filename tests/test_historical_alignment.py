from copy import deepcopy
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from financial_calculations import (FinancialDataError, course_net_schedule,
                                    session_net_from_prior, TaxRule)
from financial_reconciliation import (usage_alignment_plan, standardized_course_ledger,
                                      standardized_project_ledger)
from test_financial_reconciliation import sample
from history_proposal import build_history_proposal


class CourseRuleTests(unittest.TestCase):
    def test_fixed_price_and_last_tail(self):
        schedule = course_net_schedule('20280', 12)
        self.assertEqual(schedule.regular_net, 1610)
        self.assertEqual(schedule.final_net, 1604)
        self.assertEqual(sum(schedule.amount_for(n) for n in range(1, 13)), 19314)

    def test_single_session_and_zero_price(self):
        self.assertEqual(course_net_schedule('105', 1).amount_for(1), 100)
        self.assertEqual(course_net_schedule('0', 12).final_net, 0)

    def test_general_does_not_redivide_two_decimal_gross(self):
        # 顯式測試因子1.1：3.298/2/1.1=1.499...應取1，不能先取含稅1.65後變成2。
        rule = TaxRule(version='explicit-test-precision', divisor='1.1')
        self.assertEqual(course_net_schedule('3.298', 2, rule=rule).regular_net, 1)

    def test_fraction_exact_half_up_and_context_independent(self):
        self.assertEqual(course_net_schedule('1.575', 3).regular_net, 1)
        self.assertEqual(course_net_schedule('1.5749999999999999999999999', 3).regular_net, 0)
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(course_net_schedule('20280', 12).final_net, 1604)

    def test_last_actual_prior_not_theoretical_prior(self):
        self.assertEqual(session_net_from_prior('20280', 12, 12, [1609] * 11), 1615)
        self.assertEqual(session_net_from_prior('20280', 12, 3), 1610)

    def test_incomplete_prior_is_not_zero(self):
        with self.assertRaises(FinancialDataError):
            session_net_from_prior('20280', 12, 12, [1610])
        with self.assertRaises(FinancialDataError):
            session_net_from_prior('105', 2, 2, [None])

    def test_invalid_counts_and_negative_last_block(self):
        for value in [0, -1, '1.5', True, None, 'NaN']:
            with self.subTest(value=value), self.assertRaises(FinancialDataError):
                course_net_schedule('105', value)
        with self.assertRaises(FinancialDataError):
            course_net_schedule('57', 100)
        with self.assertRaises(FinancialDataError):
            session_net_from_prior('105', 2, 2, [101])

    def test_custom_rule_not_hardcoded(self):
        self.assertEqual(course_net_schedule('110', 2, rule=TaxRule(version='explicit', divisor='1.1')).regular_net, 50)

    def test_full_schedule_invariant_many_prices_and_counts(self):
        for gross in ['0', '105', '1200', '8888', '20280', '100.01']:
            for count in [1, 2, 3, 4, 6, 12, 25]:
                try:
                    schedule = course_net_schedule(gross, count)
                except FinancialDataError:
                    # 價格過低且堂數過多，規格不容許負最後一堂，確實交人工。
                    continue
                self.assertEqual(sum(schedule.amount_for(n) for n in range(1, count + 1)), schedule.total_net)


class HistoricalPlanTests(unittest.TestCase):
    def test_plan_retains_before_after_and_identity(self):
        result = usage_alignment_plan(sample())
        changes = [row for row in result if row['difference']]
        self.assertEqual(len(changes), 3)
        self.assertTrue(all(row['difference'] == 1 for row in changes))
        self.assertEqual(sum(row['after_net'] for row in result), 11270)

    def test_combined_usage_and_expiry_not_just_balance_fix(self):
        result = standardized_course_ledger(sample())[0]
        self.assertEqual(result['old_ledger_net'], -1)
        self.assertEqual(result['standardized_net'], 0)
        self.assertEqual(result['usage_net_saved'], 11267)
        self.assertEqual(result['usage_net_standardized'], 11270)
        self.assertEqual(result['termination_proposal']['expiry_net'], 8044)

    def test_refund_uses_normalized_usage_then_absorbs_tail(self):
        data = sample()
        data['terminations'][0].update(termination_type='refund', fee_amount='1690', refund_amount='6760')
        proposal = standardized_course_ledger(data)[0]['termination_proposal']
        self.assertEqual(proposal['fee_net'], 1610)
        self.assertEqual(proposal['refund_net'], 6434)
        self.assertEqual(proposal['fee_net'] + proposal['refund_net'], 8044)

    def test_posting_date_not_actual_date(self):
        data = sample(); data['terminations'] = []
        data['purchases'][0]['purchase_date'] = '2026-01-01'
        data['usages'][-1].update(usage_date='2026-09-08', actual_usage_date='2026-04-16')
        result = standardized_course_ledger(data, '2026-08-31')[0]
        self.assertEqual(result['usage_net_standardized'], 6 * 1610)

    def test_cutoff_before_termination_does_not_force_zero(self):
        data = sample(); data['purchases'][0]['purchase_date'] = '2026-01-01'
        result = standardized_course_ledger(data, '2026-08-24')[0]
        self.assertEqual(result['standardized_net'], 8044)
        self.assertIsNone(result['termination_proposal'])

    def test_overpayment_and_negative_balance_not_clamped(self):
        data = sample(); data['terminations'] = []
        data['payments'][0]['amount'] = '5000'
        self.assertLess(standardized_course_ledger(data)[0]['standardized_net'], 0)

    def test_missing_duplicate_orphan_bad_sequence_block(self):
        cases = [('deducted_net_amount', None), ('deducted_amount', None),
                 ('deducted_amount', '-1'), ('session_seq', 0), ('session_seq', 8),
                 ('session_seq', 2), ('purchase_id', 'missing')]
        for key, value in cases:
            data = sample(); data['usages'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(FinancialDataError):
                usage_alignment_plan(data)

    def test_shuffled_input_same_plan_and_source_unchanged(self):
        data = sample(); before = deepcopy(data)
        expected = usage_alignment_plan(data)
        data['usages'].reverse()
        self.assertEqual(usage_alignment_plan(data), expected)
        standardized_course_ledger(data)
        data['usages'].reverse()
        self.assertEqual(data, before)

    def test_project_cutoff_excludes_future_entries(self):
        data = {'projects': [{'id': 'p', 'funding_type': 'stored'}],
                'deposits': [{'id': 'd', 'project_id': 'p', 'amount': '105',
                              'transaction_type': 'opening', 'deposit_date': '2026-01-01'}],
                'entries': [{'id': 'e', 'project_id': 'p', 'line_amount': '105', 'entry_date': '2026-09-01'}]}
        self.assertEqual(standardized_project_ledger(data, '2026-08-31')[0]['standardized_net_balance'], 100)


class FullProposalTests(unittest.TestCase):
    def proposal_sample(self):
        data = sample()
        data['meta'] = {'scope': 'test-only'}
        data['operations'] = []
        data['purchases'][0]['purchase_date'] = '2026-01-01'
        return data

    def test_month_detail_and_ledger_all_reconcile(self):
        result = build_history_proposal(self.proposal_sample())
        self.assertEqual(result['usage_changed_count'], 3)
        self.assertEqual(result['usage_affected_purchase_count'], 1)
        self.assertEqual(sum(row['difference'] for row in result['usage_changes']), result['usage_net_change'])
        self.assertEqual(sum(row['difference'] for row in result['usage_by_month']), result['usage_net_change'])
        self.assertEqual(sum(row['difference'] for row in result['courses']), result['course_balance_change'])
        self.assertEqual(result['termination_proposals'][0]['after_expiry_net'], 8044)

    def test_skip_restore_is_explicit_not_passed(self):
        data = self.proposal_sample()
        self.assertFalse(build_history_proposal(data)['gate']['full_restore_test_deferred_by_user'])
        gate = build_history_proposal(data, restore_test_deferred=True)['gate']
        self.assertTrue(gate['full_restore_test_deferred_by_user'])
        self.assertFalse(gate['restorable_backup_verified'])
        self.assertFalse(gate['historical_write_performed'])

    def test_cutoff_keeps_prior_payments_and_omits_future_service_posting(self):
        data = self.proposal_sample()
        data['usages'][-1].update(usage_date='2026-09-08', actual_usage_date='2026-04-16')
        result = build_history_proposal(data, '2026-08-24')
        self.assertEqual(sum(row['count'] for row in result['usage_by_month']), 6)
        self.assertEqual(result['payments_by_month'][0]['gross'], 20280)
        self.assertEqual(result['termination_proposals'], [])

    def test_operation_and_payment_subtotals_not_month_redivision(self):
        data = self.proposal_sample()
        data['operations'] = [{'id': str(i), 'kind': 'trial', 'entry_date': '2026-09-01', 'amount': '10.01'}
                              for i in range(3)]
        result = build_history_proposal(data)
        self.assertEqual(result['operations_by_month'][0]['net_standardized'], 30)
        self.assertEqual(result['operations_by_month'][0]['gross'], Decimal('30.03'))
        self.assertEqual(sum(row['net_reconstructed'] for row in result['operation_lines']), 30)
        self.assertEqual(sum(row['net_reconstructed'] for row in result['payment_allocations']),
                         sum(row['net_standardized'] for row in result['payments_by_month']))

    def test_proposal_does_not_mutate_source(self):
        data = self.proposal_sample(); before = deepcopy(data)
        build_history_proposal(data)
        self.assertEqual(data, before)

    def test_global_precision_does_not_change_full_ledger(self):
        data = self.proposal_sample()
        expected = build_history_proposal(data)
        with localcontext() as context:
            context.prec = 3
            actual = build_history_proposal(data)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
