"""審核教練帳號標籤與提示精簡；只用虛構資料及模擬profiles查詢。"""
import ast
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from schedule_repository import ScheduleRepository
ROOT=Path(__file__).resolve().parents[1]
TEST_TEMP=ROOT/'.test-temp'
TEST_TEMP.mkdir(exist_ok=True)
tempfile.tempdir=str(TEST_TEMP)
from streamlit.testing.v1 import AppTest

SCRIPT='''
import streamlit as st
from schedule_ui import render_schedule
from schedule_demo_repository import DemoRepository
class Repo(DemoRepository):
 def coach_usernames(self,ids):
  st.session_state['username_reads']=st.session_state.get('username_reads',0)+1
  if st.session_state.get('fail_names'):raise RuntimeError('模擬讀取失敗')
  return st.session_state.get('username_map',{'demo-a':'smc001','demo-b':'smc002'})
me={'id':st.session_state.get('actor','demo-manager'),'role':st.session_state.get('role','manager'),'display_name':'虛構審核者'}
render_schedule(me,Repo(st.session_state,me))
'''


class ScheduleDisplayV31Tests(unittest.TestCase):
    def app(self,**state):
        app=AppTest.from_string(SCRIPT,default_timeout=30)
        for k,v in state.items():app.session_state[k]=v
        app.run();self.assertFalse(app.exception)
        return app

    def selector(self,app):
        return next(w for w in app.selectbox if w.label=='填寫／審核對象')

    def test_manager_and_admin_see_account_prefix_and_same_ids(self):
        for role in ('manager','admin'):
            with self.subTest(role=role):
                app=self.app(role=role)
                selector=self.selector(app)
                self.assertEqual(selector.options,['SMC001 測試教練甲','SMC002 測試教練乙'])
                self.assertEqual(selector.value,'demo-a')
                selector.set_value('demo-b').run();self.assertFalse(app.exception)
                self.assertEqual(self.selector(app).value,'demo-b')
                self.assertTrue(any('測試教練乙' in x.value for x in app.caption))
                self.assertEqual(app.session_state['schedule_demo_store']['logs'],[])

    def test_missing_or_blank_username_falls_back_to_name_only(self):
        app=self.app(username_map={'demo-a':None,'demo-b':'  '})
        self.assertEqual(self.selector(app).options,['測試教練甲','測試教練乙'])

    def test_duplicate_names_still_use_distinct_ids(self):
        source=SCRIPT.replace(' def coach_usernames(self,ids):',
            " def load(self,month):\n  data=super().load(month)\n  data['coaches'][1]['display_name']=data['coaches'][0]['display_name']\n  return data\n def coach_usernames(self,ids):")
        app=AppTest.from_string(source,default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(self.selector(app).options,['SMC001 測試教練甲','SMC002 測試教練甲'])
        self.selector(app).set_value('demo-b').run()
        self.assertEqual(self.selector(app).value,'demo-b')

    def test_coach_has_no_other_account_picker_or_username_query(self):
        app=self.app(role='coach',actor='demo-a',fail_names=True)
        self.assertFalse(any(w.label=='填寫／審核對象' for w in app.selectbox))
        self.assertNotIn('username_reads',app.session_state)

    def test_failed_username_read_stops_review_without_fake_labels(self):
        app=self.app(fail_names=True)
        self.assertTrue(any('教練帳號讀取失敗' in x.value for x in app.error))
        self.assertFalse(any(w.label=='填寫／審核對象' for w in app.selectbox))
        self.assertFalse(any(w.label=='核准班表' for w in app.button))

    def test_repository_scopes_id_and_columns_without_writes(self):
        calls=[]
        class Query:
            def select(self,columns):calls.append(('select',columns));return self
            def in_(self,key,ids):calls.append(('in',key,ids));return self
            def order(self,key):calls.append(('order',key));return self
        class Client:
            def table(self,name):calls.append(('table',name));return Query()
        def paged(builder):
            builder()
            return [{'id':'a','username':'smc001'},{'id':'b','username':None},{'id':'outside','username':'hidden'}]
        repo=ScheduleRepository(lambda:Client(),paged)
        self.assertEqual(repo.coach_usernames(['a','b','a']),{'a':'smc001','b':''})
        self.assertEqual(calls,[('table','profiles'),('select','id,username'),('in','id',['a','b']),('order','id')])
        calls.clear();self.assertEqual(repo.coach_usernames([]),{});self.assertEqual(calls,[])

    def test_repository_propagates_error_without_privileged_fallback(self):
        api=Mock(side_effect=RuntimeError('模擬拒絕'))
        repo=ScheduleRepository(api,lambda build:build())
        with self.assertRaisesRegex(RuntimeError,'模擬拒絕'):repo.coach_usernames(['a'])
        self.assertEqual(api.call_count,1)

    def test_non_admin_account_fix_and_finance_functions_unchanged(self):
        if not (ROOT/'.git').exists():self.skipTest('來源ZIP沒有Git目錄；完整邊界核對已在來源工作目錄執行')
        old=ast.parse(subprocess.check_output(['git','show','HEAD:app.py'],cwd=ROOT).decode('utf-8'))
        new=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
        for node in ast.walk(new):
            if isinstance(node,ast.Constant) and node.value=='v1.13.31':node.value='v1.13.30'
        self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(new,include_attributes=False))


if __name__=='__main__':unittest.main(verbosity=2)
