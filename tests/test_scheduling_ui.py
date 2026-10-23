from datetime import time
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]


class SchedulingUITests(unittest.TestCase):
    def app(self,source=None):
        app=(AppTest.from_string(source,default_timeout=40) if source else
             AppTest.from_file(str(ROOT/'schedule_demo.py'),default_timeout=40))
        app.run();self.assertFalse(app.exception)
        next(x for x in app.selectbox if x.label=='月份').set_value(10)
        next(x for x in app.number_input if x.label=='年份').set_value(2026)
        app.run();self.assertFalse(app.exception)
        return app
    def button(self,app,label):return next(x for x in app.button if x.label==label)
    def choose(self,app,label,value):
        next(x for x in app.selectbox if x.label==label).set_value(value).run();self.assertFalse(app.exception)
    def choose_day(self,app,day,value,actor='demo-a',target='demo-a'):
        key=self.open_day(app,day,actor,target)
        app.selectbox(key=key+'_shift').set_value(value).run();self.assertFalse(app.exception)
    def batch(self,app):
        self.choose(app,'預設班別','A')
        for label in ('套用班表',):
            self.button(app,label).click().run();self.assertFalse(app.exception)
    def confirm(self,app):
        next(x for x in app.checkbox if x.label=='已核對整月班表，確認後由主管及管理者修改').check().run()
        self.button(app,'確認儲存本月班表').click().run();self.assertFalse(app.exception)
    def tab(self,app,actor,label):
        if label=='已核准班表':app.session_state['schedule_summary_view_'+actor]='教練明細'
        app.session_state['schedule_tab_'+actor]=label;app.run();self.assertFalse(app.exception)
    def open_day(self,app,day,actor='demo-a',target='demo-a'):
        record=app.session_state['schedule_demo_store']['months'].get((target,'2026-10-01'),{'revision':0})
        key=f'schedule_day_{actor}_{target}_2026-10-{day:02d}_{record["revision"]}'
        return key
    def test_compact_personal_calendar_has_no_other_coach_or_permanent_day_form(self):
        app=self.app()
        self.assertEqual(len(app.get('popover')),31)
        captions='\n'.join(x.value for x in app.caption)
        self.assertIn('測試教練甲',captions);self.assertNotIn('測試教練乙',captions)
        self.assertFalse(any(x.label=='填寫／審核對象' for x in app.selectbox))
        self.assertEqual(sum(x.label=='班別' for x in app.selectbox),31)
        self.assertFalse(app.time_input)
    def test_simple_shift_saves_on_selection_and_preserves_manual_sunday(self):
        app=self.app();self.batch(app);self.open_day(app,4)
        before=len(app.session_state['schedule_demo_store']['logs'])
        self.choose_day(app,4,'B')
        store=app.session_state['schedule_demo_store']
        self.assertEqual(store['days'][('demo-a','2026-10-04')]['shift_code'],'B')
        self.assertEqual(len(store['logs']),before+1)
        app.run();self.assertEqual(len(app.session_state['schedule_demo_store']['logs']),before+1)
        self.button(app,'套用班表').click().run()
        self.assertEqual(app.session_state['schedule_demo_store']['days'][('demo-a','2026-10-04')]['shift_code'],'B')
    def test_custom_shift_needs_times_and_does_not_save_on_selection(self):
        app=self.app();self.choose_day(app,4,'C')
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        self.button(app,'儲存時段／備註').click().run()
        self.assertTrue(any('須填寫' in x.value for x in app.error))
        next(x for x in app.time_input if x.label=='上班時間').set_value(time(10))
        next(x for x in app.time_input if x.label=='下班時間').set_value(time(14))
        self.button(app,'儲存時段／備註').click().run();self.assertFalse(app.exception)
        row=app.session_state['schedule_demo_store']['days'][('demo-a','2026-10-04')]
        self.assertEqual((row['shift_code'],row['start_time'],row['end_time']),('C','10:00','14:00'))
    def test_submitted_lock_withdraw_and_different_coach_empty(self):
        app=self.app();self.batch(app)
        self.confirm(app);self.open_day(app,1)
        self.assertTrue(next(x for x in app.selectbox if x.label=='班別').disabled)
        self.assertTrue(self.button(app,'套用班表').disabled)
        self.assertFalse(any(x.label=='撤回待審班表' for x in app.button))
        self.assertTrue(self.button(app,'套用班表').disabled)
        self.choose(app,'測試身分','測試教練乙')
        self.assertNotIn('測試教練甲','\n'.join(x.value for x in app.caption))
        self.assertIsNone(app.selectbox(key='schedule_day_demo-b_demo-b_2026-10-01_0_shift').value)
        self.tab(app,'demo-b','已核准班表');self.assertFalse(app.dataframe)
    def test_review_publishes_and_return_removes_summary(self):
        app=self.app();self.batch(app);self.confirm(app)
        self.tab(app,'demo-a','已核准班表');self.assertFalse(app.dataframe)
        self.choose(app,'測試身分','測試主管')
        self.assertEqual(len(next(x for x in app.selectbox if x.label=='填寫／審核對象').options),2)
        self.button(app,'核准班表').click().run();self.assertFalse(app.exception)
        self.choose(app,'測試身分','測試教練乙');self.tab(app,'demo-b','已核准班表')
        self.assertEqual(list(app.table[0].value[('教練','')]),['測試教練甲'])
        self.assertEqual(app.table[0].value[('04','週日')][0],':blue-background[例假]')
        self.choose(app,'測試身分','測試主管')
        self.tab(app,'demo-manager','排班審核')
        self.choose_day(app,4,'B','demo-manager')
        self.save_manager_day(app,4,'調整週日')
        self.choose(app,'測試身分','測試教練乙');self.tab(app,'demo-b','已核准班表')
        self.assertEqual(app.table[0].value[('04','週日')][0],'B班')
        self.choose(app,'測試身分','測試教練甲');self.tab(app,'demo-a','我的排班')
        self.assertTrue(self.button(app,'套用班表').disabled)
        self.assertNotIn('異動紀錄',[x.label for x in app.tabs])
        self.assertTrue(app.session_state['schedule_demo_store']['logs'])
    def save_manager_day(self,app,day,note,actor='demo-manager',target='demo-a'):
        prefix=self.open_day(app,day,actor,target)
        shift=app.selectbox(key=prefix+'_shift').value
        app.text_input(key=prefix+'_note_'+shift).set_value(note)
        app.button(key=prefix+'_save_'+shift).click().run()
        self.assertFalse(app.exception)
    def test_reviewer_change_saves_shift_and_note_atomically_without_separate_reason(self):
        app=self.app();self.choose(app,'測試身分','測試主管')
        self.open_day(app,1,'demo-manager')
        self.choose_day(app,1,'B','demo-manager')
        self.assertFalse(app.session_state['schedule_demo_store']['days'])
        self.assertNotIn('主管／管理員異動原因',[x.label for x in app.text_input])
        self.save_manager_day(app,1,'代填備註')
        store=app.session_state['schedule_demo_store'];row=store['days'][('demo-a','2026-10-01')]
        self.assertEqual((row['shift_code'],row['note']),('B','代填備註'))
        self.assertEqual(store['logs'][-1]['reason'],'代填備註')
        self.assertEqual(len(store['logs']),1)
        app.run();self.assertEqual(len(app.session_state['schedule_demo_store']['logs']),1)
    def test_export_is_approved_only_and_same_for_reviewers(self):
        source=(ROOT/'schedule_demo.py').read_text(encoding='utf-8').replace(
            'render_schedule(me,DemoRepository(st.session_state,me))',
            'render_schedule(me,DemoRepository(st.session_state,me),lambda _:b"test-only")')
        app=self.app(source);self.batch(app)
        self.tab(app,'demo-a','已核准班表');self.assertFalse(app.get('download_button'))
        self.tab(app,'demo-a','我的排班');self.confirm(app)
        self.choose(app,'測試身分','測試主管');self.button(app,'核准班表').click().run()
        self.tab(app,'demo-manager','已核准班表');self.assertEqual(len(app.get('download_button')),1)
        self.choose(app,'測試身分','測試管理員');self.tab(app,'demo-admin','已核准班表')
        self.assertEqual(len(app.get('download_button')),1)

    def test_confirm_requires_complete_month_and_locks_without_duplicate_write(self):
        app=self.app()
        self.assertTrue(self.button(app,'確認儲存本月班表').disabled)
        self.confirm(app)
        self.assertTrue(any('未填日期' in x.value for x in app.error))
        self.button(app,'取消未確認排班操作').click().run()
        self.batch(app)
        before=len(app.session_state['schedule_demo_store']['logs'])
        self.confirm(app)
        store=app.session_state['schedule_demo_store']
        self.assertEqual(len(store['logs']),before+1)
        self.assertEqual(store['months'][('demo-a','2026-10-01')]['state'],'submitted')
        self.assertTrue(store['months'][('demo-a','2026-10-01')]['coach_locked'])
        app.run();self.assertEqual(len(app.session_state['schedule_demo_store']['logs']),before+1)
        self.tab(app,'demo-a','已核准班表');self.assertFalse(app.dataframe)

    def test_submission_explains_next_step_and_hides_draft_button(self):
        app=self.app();self.batch(app);self.confirm(app)
        self.assertTrue(any('只有主管及管理者可以修改' in x.value for x in app.info))
        self.assertFalse(any(x.label=='儲存草稿' for x in app.button))

    def test_admin_can_approve_and_return_in_same_demo_session(self):
        app=self.app();self.batch(app);self.confirm(app)
        self.choose(app,'測試身分','測試管理員')
        self.assertFalse(any(x.label=='儲存草稿' for x in app.button))
        self.button(app,'核准班表').click().run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['schedule_demo_store']['months'][('demo-a','2026-10-01')]['state'],'approved')
        self.choose_day(app,1,'B','demo-admin')
        self.save_manager_day(app,1,'管理員更正',actor='demo-admin')
        self.choose(app,'測試身分','測試教練甲')
        self.assertFalse(any(x.label in ('儲存草稿','確認儲存本月班表','撤回待審班表') for x in app.button))
        self.assertTrue(self.button(app,'套用班表').disabled)
