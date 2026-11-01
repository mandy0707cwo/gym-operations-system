"""受控完成數的離線契約與隱私檢核。"""
from copy import deepcopy
from datetime import date
from pathlib import Path
import unittest
from operations_metrics import OperationsMetrics, Period
from operations_repository import load_sources
from test_operations_management_v40 import data,purchase,usage,FakeClient,OCT


class RpcContractTests(unittest.TestCase):
    def test_production_reader_never_requests_raw_terminations(self):
        source = data()
        source['purchases'] = [purchase('p')]
        source['session_usages'] = [usage('u', 'p')]
        client = FakeClient(source)
        loaded = load_sources(client, {'role':'manager'}, OCT.start, OCT.end)
        self.assertNotIn('course_terminations', client.reads)
        self.assertNotIn('course_terminations', loaded)
        self.assertIn('rpc:operations_completed_counts', client.reads)
        self.assertEqual(OperationsMetrics(loaded).totals(OCT)['completed_courses'], 1)

    def test_admin_manager_get_identical_aggregate_and_totals(self):
        source = data()
        source['purchases'] = [purchase('p',kind='renewal'), purchase('q',kind='renewal')]
        source['session_usages'] = [usage('u','p'), usage('v','q')]
        source['course_terminations'] = [{'id':'t','purchase_id':'q','termination_date':'2026-10-01','reversed_at':None}]
        results = [OperationsMetrics(load_sources(FakeClient(source), {'role':role}, OCT.start, OCT.end)).totals(OCT)
                   for role in ('admin','manager')]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]['renewal_rate'], 2)
        self.assertEqual(results[0]['sales_net'], 2000)

    def test_rpc_error_never_falls_back_to_incomplete_data(self):
        client = FakeClient(data())
        def fail(*args):
            raise PermissionError('測試權限拒絕')
        client.rpc = fail
        with self.assertRaises(PermissionError):
            load_sources(client, {'role':'manager'}, OCT.start, OCT.end)
        self.assertNotIn('course_terminations', client.reads)

    def test_wrong_payload_or_date_rejected(self):
        for payload in (None, [{'completed_date':'2026-10-01','completed_courses':0,'reason':'不可回傳'}],
                        [{'completed_date':'2026-11-01','completed_courses':0}]):
            client = FakeClient(data())
            client.rpc = lambda *args: type('Rpc',(),{'execute':lambda self:type('Result',(),{'data':payload})()})()
            with self.assertRaises(ValueError):
                load_sources(client, {'role':'manager'}, OCT.start, OCT.end)

    def test_missing_fraction_duplicate_and_scope_mismatch_not_zero(self):
        for rows in ([{'completed_date':'2026-10-01','completed_courses':None}],
                     [{'completed_date':'2026-10-01','completed_courses':-1}],
                     [{'completed_date':'2026-10-01','completed_courses':0.5}],
                     [{'completed_date':'2026-10-01','completed_courses':0}]*2,
                     [{'completed_date':'2026-10-01','completed_courses':1}]):
            source = data()
            source.pop('course_terminations')
            source['completed_counts'] = rows
            with self.assertRaises(ValueError):
                OperationsMetrics(source)

    def test_migration_has_no_business_writes_and_role_guard_is_explicit(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root/'supabase/migrations/20261101022002_operations_completed_counts_v1_13_42.sql').read_text(encoding='utf-8')
        self.assertNotRegex(sql.lower(), r'(?m)^\s*(insert|update|delete|alter table|create policy|grant select)\b')
        self.assertIn("p.role in ('manager', 'admin')", sql)
        self.assertIn('p.active', sql)
        self.assertIn('auth.uid() is null', sql)
        self.assertIn('security invoker', sql)
        self.assertIn("set search_path = ''", sql)
        self.assertNotIn('user_metadata', sql)


if __name__ == '__main__':
    unittest.main()
