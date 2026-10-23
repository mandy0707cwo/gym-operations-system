"""v32精簡介面測試；操作虛構展示，不連正式資料庫。"""
from copy import deepcopy
import unittest
import test_scheduling_ui as previous


class ConfirmSpecialUITests(unittest.TestCase):
    def setUp(self):self.h=previous.SchedulingUITests()
    def test_manager_progress_shows_confirmed_and_unfinished_but_coach_cannot_access(self):
        app=self.h.app();self.h.batch(app);self.h.confirm(app)
        self.h.choose(app,'測試身分','測試主管');self.h.tab(app,'demo-manager','排休進度')
        self.assertFalse(app.exception)
        frame=app.dataframe[0].value
        self.assertEqual(list(frame['排休進度']),['已完成','未完成'])
        self.assertEqual(list(frame['已填日期']),['31/31','0/31'])
        self.assertEqual(list(frame['帳號']),['DEMO001','DEMO002'])
        self.h.choose(app,'測試身分','測試教練乙')
        self.assertNotIn('排休進度',[x.label for x in app.tabs]);self.assertNotIn('特殊假別設定',[x.label for x in app.tabs])
    def test_special_settings_removed_for_both_reviewers(self):
        app=self.h.app();self.h.batch(app)
        before=deepcopy(app.session_state['schedule_demo_store']['days'])
        for label,actor in [('測試主管','demo-manager'),('測試管理員','demo-admin')]:
            self.h.choose(app,'測試身分',label)
            self.assertNotIn('特殊假別設定',[x.label for x in app.tabs])
            self.assertNotIn('主管／管理員異動原因',[x.label for x in app.text_input])
            self.h.tab(app,actor,'請假登錄');self.assertFalse(app.exception)
            self.assertTrue(any(x.label=='假別' for x in app.selectbox))
        self.assertEqual(app.session_state['schedule_demo_store']['days'],before)
    def test_manager_can_fill_without_coach_confirmation_and_then_complete(self):
        app=self.h.app();self.h.choose(app,'測試身分','測試管理員')
        self.h.batch(app);self.h.button(app,'代填完成並核准').click().run();self.assertFalse(app.exception)
        row=app.session_state['schedule_demo_store']['months'][('demo-a','2026-10-01')]
        self.assertTrue(row['coach_locked']);self.assertEqual(row['state'],'approved');self.assertEqual(row['finalized_by'],'demo-admin')
        self.h.choose(app,'測試身分','測試教練甲')
        self.assertTrue(self.h.button(app,'套用班表').disabled)


if __name__=='__main__':unittest.main()
