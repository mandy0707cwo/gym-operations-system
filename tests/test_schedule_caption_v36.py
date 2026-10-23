"""v36只改入口與說明；虛構資料驗證舊分頁狀態不會跑到錯誤分頁。"""
from uuid import uuid4
import unittest
from unittest.mock import patch
import test_schedule_quota_draft as previous
from test_schedule_quota_draft import M,ADMIN
from test_schedule_leave import seed
from schedule_allowance import DEDUCT_UNITS
from schedule_demo_repository import DemoRepository


class CaptionV36Tests(unittest.TestCase):
    def setUp(self):self.h=previous.DraftUITests()
    def test_no_progress_for_reviewers_and_old_tab_resets_safely(self):
        app=self.h.app()
        for identity,actor in [('測試主管','demo-manager'),('測試管理員','demo-admin')]:
            next(x for x in app.selectbox if x.label=='測試身分').set_value(identity).run()
            self.assertNotIn('排休進度',[x.label for x in app.tabs])
            app.session_state['schedule_tab_'+actor]='排休進度';app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any(x.label=='填寫／審核對象' for x in app.selectbox))
            app.session_state['schedule_tab_'+actor]='請假登錄';app.run();self.assertFalse(app.exception)
            self.assertTrue(any(x.label=='請假教練' for x in app.selectbox))
    def test_exact_allowance_caption_without_confirmer(self):
        app=self.h.app();state={'schedule_demo_store':app.session_state['schedule_demo_store']}
        DemoRepository(state,ADMIN).allowance_save(str(uuid4()),{'p_month':M,'p_expected_revision':1,'p_payload':{
            'holidays':[{'name':'虛構假日甲','original_date':'2026-10-10','observed_date':'2026-10-12'},
                        {'name':'虛構假日乙','original_date':'2026-10-25','observed_date':'2026-10-26'}],
            'deduct_units':dict(DEDUCT_UNITS),'note':'虛構測試日曆'}})
        app.session_state['schedule_demo_store']=state['schedule_demo_store'];app.run();self.assertFalse(app.exception)
        captions=[x.value for x in app.caption]
        self.assertIn('本月可休：星期六5天＋國定假日／補假2天；',captions)
        self.assertFalse(any('來源：' in x or '已由' in x for x in captions))
    def test_approved_headcount_has_only_new_legend_and_keeps_details(self):
        app=self.h.app();state={'schedule_demo_store':app.session_state['schedule_demo_store']};seed(state)
        app.session_state['schedule_demo_store']=state['schedule_demo_store']
        app.session_state['schedule_tab_demo-a']='已核准班表'
        with patch('schedule_headcount_ui.count_grid',return_value=None):app.run()
        self.assertFalse(app.exception);captions=[x.value for x in app.caption]
        self.assertIn('※上班人數／原排。點選後查看班別、姓名與時間。',captions)
        self.assertIn('※星號【＊】代表當日非常態班(半日休、請假)',captions)
        for old in ('格內＝','半日休：時段','只依核准班表','A＝09:00','展開下方查看'):
            self.assertFalse(any(old in x for x in captions))
