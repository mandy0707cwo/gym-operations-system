import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import unittest
from uuid import uuid4
from test_idempotency_database import sql,actor,COACH,OTHER,ADMIN


class SchedulingDatabaseTests(unittest.TestCase):
    def setUp(self):
        # 每例用不同過去月份，明確驗證沒有跨月鎖。
        counter=int(sql("select count(*) from public.staff_schedule_months")[0])
        self.month=f'{2000+counter//12:04d}-{counter%12+1:02d}-01'
    def revision(self,coach=COACH):
        return int(sql(f"select coalesce((select revision from public.staff_schedule_months where coach_id='{coach}' and month_start='{self.month}'),0)")[0])
    def query(self,action,payload=None,coach=COACH,token=None,rev=None):
        if action=='fill' and payload is None:
            current=sql(f"select base_shift from public.staff_schedule_preferences where coach_id='{coach}'")
            payload={'base_shift':current[0] if current else None}
        encoded=json.dumps(payload or {}).replace("'","''")
        return f"select public.staff_schedule_command('{token or uuid4()}','{coach}','{self.month}',{self.revision(coach) if rev is None else rev},'{action}','{encoded}'::jsonb)"
    def send(self,action,payload=None,who=COACH,**kwargs):return json.loads(actor(self.query(action,payload,**kwargs),who))
    def fill(self):self.send('default',{'base_shift':'A'});self.send('fill')
    def test_fill_preserves_sunday_and_other_coach_reads_only_approved(self):
        self.fill()
        data=sql(f"select work_date||':'||shift_code from public.staff_schedule_days where coach_id='{COACH}' and month_start='{self.month}' order by work_date")
        for row in data:
            d,code=row.split(':');self.assertEqual(code,'regular_off' if date.fromisoformat(d).weekday()==6 else 'A')
        sunday=next(x[:10] for x in data if x.endswith('regular_off'))
        self.send('save',{'work_date':sunday,'shift_code':'B'})
        self.send('fill')
        self.assertEqual(sql(f"select shift_code from public.staff_schedule_days where coach_id='{COACH}' and work_date='{sunday}'")[0],'B')
        visible=int(actor(f"select count(*) from public.staff_schedule_days where month_start='{self.month}'",OTHER))
        self.assertEqual(visible,0)
        self.assertEqual(actor(f"select count(*) from public.staff_schedule_months where coach_id='{COACH}' and month_start='{self.month}'",OTHER),'0')
        self.assertEqual(actor(f"select count(*) from public.staff_schedule_preferences where coach_id='{COACH}'",OTHER),'0')
        self.assertEqual(int(actor(f"select count(*) from public.staff_schedule_days where month_start='{self.month}'")),len(data))
        self.assertEqual(int(actor(f"select count(*) from public.staff_schedule_days where month_start='{self.month}'",ADMIN)),len(data))
        self.send('submit')
        self.assertEqual(actor(f"select count(*) from public.staff_schedule_days where month_start='{self.month}'",OTHER),'0')
        self.send('approve',who=ADMIN)
        self.assertEqual(int(actor(f"select count(*) from public.staff_schedule_days where month_start='{self.month}'",OTHER)),len(data))
        self.send('return',{'reason':'修正'},who=ADMIN)
        self.assertEqual(actor(f"select count(*) from public.staff_schedule_days where month_start='{self.month}'",OTHER),'0')
    def test_review_lock_withdraw_return_and_reason(self):
        self.fill();self.send('submit')
        with self.assertRaisesRegex(RuntimeError,'不可修改'):self.send('fill')
        with self.assertRaisesRegex(RuntimeError,'只有主管'):self.send('withdraw')
        self.send('approve',who=ADMIN)
        with self.assertRaises(RuntimeError):self.send('withdraw')
        with self.assertRaisesRegex(RuntimeError,'原因'):self.send('return',who=ADMIN)
        self.send('return',{'reason':'測試退回'},who=ADMIN)
        with self.assertRaisesRegex(RuntimeError,'只有主管'):self.send('save',{'work_date':self.month,'shift_code':'full_off'})
        self.send('save',{'work_date':self.month,'shift_code':'full_off','reason':'主管更正'},who=ADMIN)
        self.assertTrue(int(actor(f"select count(*) from public.staff_schedule_logs where month_start='{self.month}'"))>0)
    def test_other_coach_cannot_write_or_review_or_read_other_logs(self):
        self.fill()
        with self.assertRaisesRegex(RuntimeError,'自己的'):self.send('fill',who=OTHER)
        with self.assertRaises(RuntimeError):self.send('approve')
        self.assertEqual(actor(f"select count(*) from public.staff_schedule_logs where coach_id='{COACH}'",OTHER),'0')
    def test_direct_dml_and_private_receipts_denied(self):
        self.fill()
        for q in [f"update public.staff_schedule_months set state='approved' where coach_id='{COACH}'",
                  'delete from public.staff_schedule_days','insert into public.staff_schedule_preferences(coach_id,base_shift) values (null,\'A\')',
                  'select * from schedule_private.requests']:
            with self.subTest(q=q),self.assertRaisesRegex(RuntimeError,'permission denied'):actor(q)
    def test_same_operation_replay_and_changed_content(self):
        token=str(uuid4());query=self.query('default',{'base_shift':'A'},token=token)
        a=actor(query);b=actor(query);self.assertEqual(json.loads(a),json.loads(b))
        with self.assertRaisesRegex(RuntimeError,'內容不同'):actor(self.query('default',{'base_shift':'B'},token=token))

    def test_same_key_two_connections_returns_identical_result_once(self):
        token=str(uuid4());query=self.query('default',{'base_shift':'A'},token=token)
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda _:json.loads(actor(query)),range(2)))
        self.assertEqual(result[0],result[1]);self.assertEqual(self.revision(),1)
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_logs where coach_id='{COACH}' and month_start='{self.month}'")[0],'1')

    def test_success_replay_after_approval_does_not_reopen_month(self):
        query=self.query('default',{'base_shift':'A'})
        original=json.loads(actor(query));self.send('fill');self.send('submit');self.send('approve',who=ADMIN)
        self.assertEqual(json.loads(actor(query)),original)
        self.assertEqual(sql(f"select state from public.staff_schedule_months where coach_id='{COACH}' and month_start='{self.month}'")[0],'approved')
    def test_cancelled_key_blocks_late_request(self):
        token=str(uuid4());actor(f"select public.staff_schedule_operation('{token}',true)")
        with self.assertRaisesRegex(RuntimeError,'取消'):actor(self.query('default',{'base_shift':'A'},token=token))
    def test_two_keys_stale_revision_only_one_succeeds(self):
        self.send('default',{'base_shift':'A'});rev=self.revision()
        def send(_):
            try:return actor(self.query('fill',rev=rev))
            except RuntimeError as exc:return str(exc)
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(send,range(2)))
        self.assertEqual(sum('班表已更新' in x for x in result),1)
    def test_missing_days_bad_date_or_custom_time_roll_back(self):
        count=sql('select count(*) from public.staff_schedule_months')[0]
        with self.assertRaisesRegex(RuntimeError,'未填日期'):self.send('submit')
        self.assertEqual(sql('select count(*) from public.staff_schedule_months')[0],count)
        for payload in ({'work_date':self.month,'shift_code':'C'},
                        {'work_date':'2099-01-01','shift_code':'A'},
                        {'work_date':self.month,'shift_code':'other'},
                        {'work_date':self.month,'shift_code':'half_off','start_time':'18:00','end_time':'09:00'}):
            with self.subTest(payload=payload),self.assertRaises(RuntimeError):self.send('save',payload)
    def test_inactive_or_shared_role_cannot_read_or_write(self):
        self.fill()
        for change in ("active=false","role='shared_coach'"):
            sql(f"update public.profiles set {change} where id='{COACH}'")
            try:
                with self.assertRaisesRegex(RuntimeError,'權限|停用'):self.send('fill')
                with self.assertRaisesRegex(RuntimeError,'權限|停用'):actor('select * from public.staff_schedule_days')
                with self.assertRaisesRegex(RuntimeError,'權限|停用'):actor('select * from public.staff_schedule_logs')
            finally:sql(f"update public.profiles set active=true,role='coach' where id='{COACH}'")
    def test_manager_correction_uses_note_without_separate_reason_and_preserves_audit(self):
        self.fill();self.send('submit')
        sql(f"update public.profiles set role='manager' where id='{ADMIN}'")
        try:
            self.send('approve',who=ADMIN)
            self.send('save',{'work_date':self.month,'shift_code':'public_off','note':'主管更正備註'},who=ADMIN)
            self.assertEqual(sql(f"select note from public.staff_schedule_days where coach_id='{COACH}' and work_date='{self.month}'")[0],'主管更正備註')
            self.assertEqual(sql(f"select reason from public.staff_schedule_logs where coach_id='{COACH}' and month_start='{self.month}' and action='save' order by created_at desc limit 1")[0],'主管更正備註')
            self.assertEqual(sql(f"select state from public.staff_schedule_months where coach_id='{COACH}' and month_start='{self.month}'")[0],'approved')
        finally:sql(f"update public.profiles set role='admin' where id='{ADMIN}'")

    def test_valid_custom_half_day_other_and_all_off_types(self):
        for seq,code in enumerate(('C','half_off','other','full_off','weekend','regular_off','public_off'),1):
            payload={'work_date':self.month[:8]+f'{seq:02d}','shift_code':code,'start_time':'10:00','end_time':'14:30','note':'測試說明'}
            if code=='public_off':self.send('save',dict(payload,reason='主管設定公休'),who=ADMIN)
            else:self.send('save',payload)
        rows=sql(f"select count(*) from public.staff_schedule_days where coach_id='{COACH}' and month_start='{self.month}'")
        self.assertEqual(rows[0],'7')
        self.assertEqual(sql(f"select count(*) from public.staff_schedule_days where coach_id='{COACH}' and month_start='{self.month}' and start_time is null")[0],'4')

    def test_stale_default_shift_rejected_and_service_backup_read(self):
        self.send('default',{'base_shift':'A'})
        with self.assertRaisesRegex(RuntimeError,'預設班別已變更'):self.send('fill',{'base_shift':'B'})
        result=sql("begin;set local role service_role;select count(*) from public.staff_schedule_months;rollback;")
        self.assertTrue(result)

    def test_full_migration_fresh_install_rollback_preserves_business(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parents[1]/'supabase/migrations/20261021083833_staff_scheduling_v1_13_22.sql').read_text(encoding='utf-8')
        visibility=(Path(__file__).resolve().parents[1]/'supabase/migrations/20261021091712_schedule_approved_visibility_v1_13_23.sql').read_text(encoding='utf-8')
        # 在測試本身的外層交易內驗證五版連續安裝，不允許migration提交外層交易。
        source+=visibility.split('begin;',1)[1].rsplit('commit;',1)[0]
        root=Path(__file__).resolve().parents[1]
        source+=(root/'supabase/migrations/20261021100055_schedule_allowance_v1_13_25.sql').read_text(encoding='utf-8')
        source+=(root/'supabase/migrations/20261021152424_schedule_leave_v1_13_26.sql').read_text(encoding='utf-8')
        source+=(root/'supabase/migrations/20261021160257_schedule_apply_v1_13_27.sql').read_text(encoding='utf-8')
        snapshot="select (select count(*) from public.purchases)||':'||(select count(*) from public.purchase_payments)||':'||(select count(*) from public.session_usages)"
        before=sql(snapshot)[0]
        # 只在明確的本機虛構庫、可回滾交易內重新建置本模組，不清除其他schema。
        leaves_before=sql('select count(*) from public.staff_schedule_leaves')[0]
        query="begin;drop function public.staff_schedule_leave_save(uuid,uuid,uuid,date,integer,integer,text,jsonb),public.staff_schedule_leave_snapshot(date),public.staff_schedule_allowance_save(uuid,date,integer,jsonb),public.staff_schedule_allowance_snapshot(date);"
        query+="drop table public.staff_schedule_leave_logs,public.staff_schedule_leaves,public.staff_schedule_allowance_logs,public.staff_schedule_allowances,public.staff_schedule_logs,public.staff_schedule_days,public.staff_schedule_preferences,public.staff_schedule_months;"
        query+="drop function if exists public.staff_schedule_snapshot(date);drop function public.staff_schedule_command(uuid,uuid,date,integer,text,jsonb),public.staff_schedule_operation(uuid,boolean);drop schema schedule_private cascade;"
        result=sql(query+source+"select count(*) from public.staff_schedule_months;rollback;")
        self.assertEqual(result[-1],'0');self.assertEqual(sql(snapshot)[0],before)
        self.assertEqual(sql('select count(*) from public.staff_schedule_leaves')[0],leaves_before)

    def test_snapshot_hides_drafts_publishes_approved_and_inactive_denied(self):
        self.fill()
        data=json.loads(actor(f"select public.staff_schedule_snapshot('{self.month}')",OTHER))
        self.assertTrue(len(data['coaches'])>=2)
        self.assertEqual(data['days'],[]);self.assertEqual(data['months'],[])
        self.assertNotIn(COACH,{x['coach_id'] for x in data['preferences']})
        owner=json.loads(actor(f"select public.staff_schedule_snapshot('{self.month}')"))
        self.assertTrue(owner['days']);self.assertEqual(len(owner['months']),1)
        self.send('submit');self.send('approve',who=ADMIN)
        approved=json.loads(actor(f"select public.staff_schedule_snapshot('{self.month}')",OTHER))
        self.assertTrue(approved['days']);self.assertEqual(approved['months'][0]['state'],'approved')
        sql(f"update public.profiles set active=false where id='{OTHER}'")
        try:
            with self.assertRaisesRegex(RuntimeError,'權限|停用'):actor(f"select public.staff_schedule_snapshot('{self.month}')",OTHER)
        finally:sql(f"update public.profiles set active=true where id='{OTHER}'")
