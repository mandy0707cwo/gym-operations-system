from copy import deepcopy
from datetime import date,time
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from scheduling import dates_in_month,day_payload,EDITABLE_SHIFTS
from schedule_headcounts import headcounts,headcount_details,query_window
from schedule_headcount_component import JS,CSS
from schedule_allowance import normalize_allowance,DEDUCT_UNITS

ROOT=Path(__file__).resolve().parents[1]
MONTH='2026-10-01'


def fixture():
    coaches=[{'id':x,'display_name':'同名教練' if x in ('a','b') else '教練'+x} for x in ('a','b','c','d','e')]
    data={'months':[{'coach_id':x['id'],'coach_name':x['display_name'],'month_start':MONTH,'state':'approved'} for x in coaches],
          'days':[dict(day_payload(d,'A'),coach_id=x['id'],month_start=MONTH) for d in dates_in_month(MONTH) for x in coaches]}
    def shift(coach,code,start=None,end=None,note=''):
        row=next(x for x in data['days'] if x['coach_id']==coach and x['work_date']=='2026-10-01')
        row.update(day_payload('2026-10-01',code,start,end,note))
    shift('c','B');shift('d','C','10:00','16:00');shift('e','half_off','13:00','18:00')
    return coaches,data


def slot(coach,start,end,day='2026-10-01'):
    return {'coach_id':coach,'work_date':day,'start_time':start,'end_time':end,'minutes':1,'reason':'不可傳送的私密原因','leave_kind':'sick'}


def cell(result,group='A',day='2026-10-01'):
    return next(x for row in result['rows'] if row['group']==group for x in row['cells'] if x['date']==day)


class HeadcountRulesTests(unittest.TestCase):
    def test_two_available_one_absent_and_all_absent(self):
        c,d=fixture()
        self.assertEqual(cell(headcounts(c,d,MONTH,[]))['text'],'2/2')
        self.assertEqual(cell(headcounts(c,d,MONTH,[slot('a','09:00','18:00')]))['text'],'1/2')
        self.assertEqual(cell(headcounts(c,d,MONTH,[slot(x,'09:00','18:00') for x in ('a','b')]))['text'],'0/2')
    def test_partial_leaves_do_not_remove_whole_day(self):
        c,d=fixture();leaves=[slot(x,'13:00','16:00') for x in ('a','b')]
        result=headcounts(c,d,MONTH,leaves)
        self.assertEqual(cell(result)['text'],'2/2＊')
        self.assertEqual(cell(headcounts(c,d,MONTH,leaves,(13*60,16*60)))['text'],'0/2＊')
        self.assertEqual(cell(headcounts(c,d,MONTH,leaves,(9*60,10*60)))['text'],'2/2')
        details=headcount_details(result,{'group':'A','date':'2026-10-01'})
        self.assertEqual(details[0]['實際上班時段'],'09:00–13:00、16:00–18:00')
        self.assertEqual(details[0]['請假'],'部分請假')
        self.assertNotIn('狀況',details[0]);self.assertNotIn('扣除不在班後時段',details[0])
        self.assertEqual(len(details),2)  # 同名依coach_id區分，不合併。
        self.assertNotIn('私密',str(details));self.assertNotIn('sick',str(details))
    def test_adjacent_overlapping_and_duplicate_leave_union(self):
        c,d=fixture();leaves=[slot('a','09:00','13:00'),slot('a','12:00','16:00'),slot('a','16:00','18:00')]*2
        self.assertEqual(cell(headcounts(c,d,MONTH,leaves))['text'],'1/2')
    def test_window_requires_full_coverage_and_correct_boundaries(self):
        c,d=fixture()
        self.assertEqual(cell(headcounts(c,d,MONTH,[],(9*60,10*60)),'B')['text'],'0/0')
        self.assertEqual(cell(headcounts(c,d,MONTH,[],(15*60,17*60)),'C')['text'],'1/2＊')
        self.assertEqual(cell(headcounts(c,d,MONTH,[slot('a','13:00','14:00')],(12*60,13*60)))['text'],'2/2')
        self.assertEqual(query_window('整日',None,None),None)
        self.assertEqual(query_window('指定時段',time(13),time(14)),(780,840))
        for args in [('指定時段',None,None),('指定時段',time(16),time(13)),('錯誤',None,None)]:
            with self.assertRaises(ValueError):query_window(*args)
    def test_off_excluded_half_other_separate_and_unknown_not_zero(self):
        c,d=fixture();row=next(x for x in d['days'] if x['coach_id']=='a' and x['work_date']=='2026-10-01')
        row.update(day_payload('2026-10-01','weekend'))
        result=headcounts(c,d,MONTH,[])
        self.assertEqual(cell(result)['text'],'1/1');self.assertEqual(cell(result,'C')['text'],'2/2＊')
        self.assertEqual(cell(result,'total')['text'],'4/4＊')
        row.update(day_payload('2026-10-01','other',note='未填時段，待確認'))
        result=headcounts(c,d,MONTH,[])
        self.assertEqual(cell(result,'C')['text'],'—/3＊');self.assertEqual(cell(result,'total')['text'],'—/5＊')
    def test_four_rows_and_each_coach_only_once_with_original_shift_preserved(self):
        c,d=fixture();before=deepcopy(d);result=headcounts(c,d,MONTH,[])
        self.assertEqual([x['label'] for x in result['rows']],['A班','B班','C班','合計'])
        self.assertEqual(cell(result,'total')['text'],'5/5＊')
        self.assertEqual(sum(cell(result,g)['original'] for g in ('A','B','C')),5)
        self.assertEqual(len({x['coach'] for x in result['staff'][('2026-10-01','total')]}),5)
        self.assertEqual({x['班別'] for x in headcount_details(result,{'group':'C','date':'2026-10-01'})},{'C班','半日休'})
        self.assertEqual(d,before)
    def test_half_day_unique_a_b_overlap_and_outside(self):
        from schedule_headcounts import summary_group
        self.assertEqual(summary_group('half_off',540,780),'A')
        self.assertEqual(summary_group('half_off',1020,1260),'B')
        self.assertEqual(summary_group('half_off',780,1080),'C')
        self.assertEqual(summary_group('half_off',480,600),'C')
        c,d=fixture();row=next(x for x in d['days'] if x['coach_id']=='e' and x['work_date']=='2026-10-01')
        row.update(day_payload('2026-10-01','half_off','09:00','13:00'))
        result=headcounts(c,d,MONTH,[])
        self.assertEqual(cell(result)['text'],'3/3＊');self.assertEqual(cell(result,'C')['text'],'1/1')
        self.assertIn('半日休',{x['班別'] for x in headcount_details(result,{'group':'A','date':'2026-10-01'})})
    def test_other_with_time_always_c_and_missing_time_never_available(self):
        c,d=fixture();row=next(x for x in d['days'] if x['coach_id']=='a' and x['work_date']=='2026-10-01')
        row.update(day_payload('2026-10-01','other','09:00','18:00','其他工作'))
        result=headcounts(c,d,MONTH,[])
        self.assertEqual(cell(result)['text'],'1/1');self.assertEqual(cell(result,'C')['text'],'3/3＊')
        row.update(day_payload('2026-10-01','other',note='待確認'))
        result=headcounts(c,d,MONTH,[],(540,600))
        self.assertEqual(cell(result,'C')['text'],'—/1＊')
        self.assertIsNone(result['staff'][('2026-10-01','C')][0]['available'])
        self.assertIn('待確認',headcount_details(result,{'group':'C','date':'2026-10-01'})[0]['請假'])
    def test_half_day_group_not_changed_by_leave_or_query_and_full_absence_zero(self):
        c,d=fixture();row=next(x for x in d['days'] if x['coach_id']=='e' and x['work_date']=='2026-10-01')
        row.update(day_payload('2026-10-01','half_off','17:00','21:00'))
        result=headcounts(c,d,MONTH,[slot('e','17:00','21:00')],(1080,1140))
        self.assertEqual(cell(result,'B')['text'],'1/2＊')
        details=headcount_details(result,{'group':'B','date':'2026-10-01'})
        half=next(x for x in details if x['班別']=='半日休')
        self.assertEqual(half['實際上班時段'],'無')
        self.assertEqual(half['請假'],'整段請假')
    def test_only_approved_complete_valid_data_and_selection(self):
        c,d=fixture();before=deepcopy(d)
        result=headcounts(c,d,MONTH,[]);self.assertEqual(d,before)
        for selection in ({'group':'bad','date':'2026-10-01'},{'group':'half_off','date':'2026-10-01'},{'group':'A','date':'2026-11-01'}):
            with self.assertRaises(ValueError):headcount_details(result,selection)
        for bad in (dict(d,days=d['days'][:-1]),dict(d,days=d['days']+d['days'][:1]),dict(d,months=[])):
            with self.assertRaises(ValueError):headcounts(c,bad,MONTH,[])
        d['months'][0]['state']='returned'
        self.assertEqual(cell(headcounts(c,d,MONTH,[slot('a','09:00','18:00')]))['text'],'1/1')
    def test_component_has_only_safe_table_data_and_no_external_loading(self):
        c,d=fixture();result=headcounts(c,d,MONTH,[slot('a','09:00','18:00')])
        payload={k:result[k] for k in ('headers','rows')}
        self.assertNotIn('教練a',str(payload));self.assertNotIn('coach_id',str(payload));self.assertNotIn('reason',str(payload))
        self.assertNotIn('innerHTML',JS);self.assertNotIn('fetch(',JS);self.assertNotIn('postMessage',JS)
        self.assertIn('setTriggerValue',JS);self.assertIn('--st-text-color',CSS)
        self.assertNotIn('weekend',EDITABLE_SHIFTS)


class HeadcountUITests(unittest.TestCase):
    def app(self):
        from test_schedule_leave import seed
        app=AppTest.from_file(str(ROOT/'schedule_demo.py'),default_timeout=40).run()
        app.number_input[0].set_value(2026);next(x for x in app.selectbox if x.label=='月份').set_value(10)
        app.run();state={'schedule_demo_store':app.session_state['schedule_demo_store']};seed(state)
        app.session_state['schedule_demo_store']=state['schedule_demo_store']
        app.session_state['schedule_tab_demo-a']='已核准班表';app.run();self.assertFalse(app.exception)
        return app
    def test_month_only_no_query_controls_and_click_details(self):
        with patch('schedule_headcount_ui.count_grid',return_value=None):
            app=self.app();self.assertFalse(any(x.label=='查詢人數' for x in app.button))
            self.assertIn('班別人數',next(x for x in app.get('button_group') if x.label=='班表顯示').options)
            self.assertFalse(app.time_input)
            self.assertFalse(any(x.label=='人數查詢方式' for x in app.selectbox))
            app.session_state['headcount_demo-a_2026-10-01_query']=(780,960)
            app.session_state['_schedule_force_tab_demo-a']='已核准班表'
            app.run();self.assertTrue(any('※上班人數／原排。' in x.value for x in app.caption))
        with patch('schedule_headcount_ui.count_grid',return_value={'group':'A','date':'2026-10-01','context':"2026-10-01|whole-month-v29"}):
            app.session_state['_schedule_force_tab_demo-a']='已核准班表'
            app.run();self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe[0].value),2)
            self.assertEqual(set(app.dataframe[0].value['教練']),{'測試教練甲','測試教練乙'})
        with patch('schedule_headcount_ui.count_grid',return_value={'group':'A','date':'2026-10-02','context':"2026-10-01|whole-month-v29"}) as grid:
            app.session_state['_schedule_force_tab_demo-a']='已核准班表'
            app.run();self.assertFalse(app.exception)
            self.assertEqual(grid.call_args.kwargs['selected'],{'group':'A','date':'2026-10-02'})
            self.assertEqual(set(app.dataframe[0].value['日期'].astype(str)),{'2026-10-02'})
        with patch('schedule_headcount_ui.count_grid',return_value={'group':'A','date':'2026-11-01','context':'old'}):
            app.session_state['_schedule_force_tab_demo-a']='已核准班表'
            app.run();self.assertTrue(app.error)
    def test_missing_other_time_warns_without_rewriting_store(self):
        with patch('schedule_headcount_ui.count_grid',return_value=None):
            app=self.app();store=deepcopy(app.session_state['schedule_demo_store'])
            row=next(x for x in store['days'].values() if x['work_date']=='2026-10-01')
            row.update(day_payload('2026-10-01','other',note='待確認'))
            app.session_state['schedule_demo_store']=store
            app.session_state['_schedule_force_tab_demo-a']='已核准班表'
            app.run();self.assertFalse(app.exception)
            self.assertTrue(any('待確認' in x.value for x in app.warning))
            self.assertEqual(app.session_state['schedule_demo_store'],store)
    def test_removed_text_and_weekend_choice_keep_history(self):
        app=AppTest.from_file(str(ROOT/'schedule_demo.py'),default_timeout=40).run()
        for x in app.selectbox:
            if x.label=='班別':self.assertNotIn('週末',x.options)
        from schedule_demo_repository import DemoRepository
        from test_schedule_leave import ADMIN
        state={'schedule_demo_store':app.session_state['schedule_demo_store']}
        repo=DemoRepository(state,ADMIN)
        repo.allowance_save('test',{ 'p_month':MONTH,'p_expected_revision':0,
            'p_payload':{'holidays':[],'deduct_units':DEDUCT_UNITS,'note':'測試'}})
        app.session_state['schedule_demo_store']=state['schedule_demo_store']
        app.number_input[0].set_value(2026);next(x for x in app.selectbox if x.label=='月份').set_value(10)
        app.run()
        self.assertNotIn('扣算方式：','\n'.join(x.value for x in app.markdown))
        self.assertEqual(repo.allowance_load(MONTH)['deduct_units']['weekend'],0)
