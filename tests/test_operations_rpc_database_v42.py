"""真實PostgreSQL角色測試；固定本機假資料庫，不接受正式連線設定。"""
import json
import unittest
from operations_db import sql,actor,fingerprint,ADMIN,MANAGER,COACH,SHARED,INACTIVE,MISSING,MIGRATION

QUERY = "select coalesce(jsonb_agg(to_jsonb(t) order by completed_date),'[]'::jsonb)::text from public.operations_completed_counts('2026-10-01','2026-10-31') t"


class RpcDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.before = fingerprint()

    def tearDown(self):
        self.assertEqual(self.before, fingerprint())

    def test_manager_admin_same_aggregate_without_raw_termination_access(self):
        result = json.loads(actor(QUERY, ADMIN))
        self.assertEqual(result, json.loads(actor(QUERY, MANAGER)))
        self.assertEqual(result, [{'completed_date':'2026-10-02','completed_courses':1},
                                  {'completed_date':'2026-10-07','completed_courses':2},
                                  {'completed_date':'2026-10-16','completed_courses':1},
                                  {'completed_date':'2026-10-20','completed_courses':1}])
        self.assertEqual(actor('select count(*) from public.course_terminations', MANAGER), '0')
        self.assertEqual(actor('select count(*) from public.course_terminations', ADMIN), '4')
        self.assertTrue(all(set(row)=={'completed_date','completed_courses'} for row in result))

    def test_coach_shared_inactive_and_missing_cannot_use_either_entry(self):
        for who in (COACH, SHARED, INACTIVE, MISSING):
            for query in (QUERY, "select * from operations_private.completed_counts('2026-10-01','2026-10-31')"):
                with self.subTest(who=who, query=query):
                    with self.assertRaisesRegex(RuntimeError, '僅限'):
                        actor(query, who)

    def test_anonymous_and_no_identity_denied(self):
        with self.assertRaisesRegex(RuntimeError, 'permission denied'):
            sql('set role anon;' + QUERY)
        with self.assertRaisesRegex(RuntimeError, '僅限'):
            sql('set role authenticated;' + QUERY)

    def test_missing_or_reversed_dates_rejected(self):
        for args in ("null,'2026-10-31'", "'2026-10-01',null", "'2026-11-01','2026-10-01'"):
            with self.assertRaisesRegex(RuntimeError, '有效的統計日期'):
                actor('select * from public.operations_completed_counts(' + args + ')')

    def test_public_invoker_private_definer_and_exact_acl(self):
        flags = sql("select n.nspname||':'||p.prosecdef||':'||array_to_string(p.proconfig,',') from pg_proc p join pg_namespace n on n.oid=p.pronamespace where p.proname in ('operations_completed_counts','completed_counts') order by n.nspname")
        self.assertEqual(len(flags), 2)
        self.assertIn('operations_private:true:search_path=""', flags)
        self.assertIn('public:false:search_path=""', flags)
        for name in ('public.operations_completed_counts(date,date)', 'operations_private.completed_counts(date,date)'):
            self.assertEqual(sql(f"select has_function_privilege('anon','{name}','execute')::text")[0], 'false')
            self.assertEqual(sql(f"select has_function_privilege('authenticated','{name}','execute')::text")[0], 'true')

    def test_repeat_migration_does_not_change_sources_or_raw_policy(self):
        policy = sql("select qual from pg_policies where tablename='course_terminations'")
        sql(MIGRATION.read_text(encoding='utf-8'))
        self.assertEqual(policy, sql("select qual from pg_policies where tablename='course_terminations'"))
        self.assertEqual(actor(QUERY, MANAGER), actor(QUERY, ADMIN))

    def test_calendar_boundary_cross_month_and_zero_result(self):
        self.assertEqual(actor("select sum(completed_courses) from public.operations_completed_counts('2026-10-02','2026-10-02')"), '1')
        self.assertEqual(actor("select count(*) from public.operations_completed_counts('2026-09-01','2026-09-30')"), '0')
        self.assertEqual(actor("select sum(completed_courses) from public.operations_completed_counts('2026-11-01','2026-11-30')"), '1')

    def test_immediate_profile_deactivation_is_not_stale_jwt_authorization(self):
        self.assertEqual(actor('select count(*) from public.operations_completed_counts(\'2026-10-01\',\'2026-10-31\')', MANAGER), '4')
        with self.assertRaisesRegex(RuntimeError, '僅限'):
            sql("begin;update public.profiles set active=false where id='" + MANAGER + "';"
                "select set_config('request.jwt.claim.sub','" + MANAGER + "',true);set local role authenticated;" + QUERY + ';rollback;')


if __name__ == '__main__':
    unittest.main()
