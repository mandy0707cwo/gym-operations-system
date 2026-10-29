"""真實報表函式與下載回歸，僅用虛構會員及金額。"""
from datetime import date
from copy import deepcopy
import unittest
import test_online_finance as base
from test_online_finance import tables
from test_termination_reversal import samples
from test_financial_backup import load_functions


def reversed_tables():
    data=tables();term,rev=samples();term.update(completion_bonus_eligible=False,completion_bonus_coach_id=None,reason='虛構中止',created_at='2026-09-30T00:00:00Z')
    data['purchases'][0]['status']='active'
    rev['original_purchase']=deepcopy(data['purchases'][0])
    data['course_terminations']=[term];data['course_termination_reversals']=[rev]
    return data


class ReversalScreenTests(unittest.TestCase):
    app=base.FinancialScreenTests.app

    def test_complete_backup_shows_both_events_and_restored_balance(self):
        result=load_functions()['_financial_backup_frames'](reversed_tables())
        events=result['財務-課程中止']
        self.assertEqual(sorted(events['實際退費金額（未稅）'].tolist()),[-1066,1066])
        self.assertEqual(result['財務-預收餘額明細'].iloc[0]['實際預收剩餘金額'],1400)
    def test_historical_balance_and_download_before_after_reversal(self):
        app=self.app('general',tables=reversed_tables(),general_query_main_tab='預收餘額查詢',general_balance_mode='預收餘額（未稅）')
        for day,expected in [(date(2026,9,30),0),(date(2026,10,15),1333)]:
            app.date_input[0].set_value(day);app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.dataframe[0].value.iloc[0]['餘額（未稅）'],expected)
            self.assertEqual(app.session_state['exports']['預收餘額（未稅）'].iloc[0]['餘額（未稅）'],expected)

    def test_monthly_original_stays_and_reversal_is_negative_later(self):
        app=self.app('financial',tables=reversed_tables(),financial_report_view='每月報表')
        for start,end,expected,label in [(date(2026,9,1),date(2026,9,30),1066,'退費中止'),(date(2026,10,1),date(2026,10,28),-1066,'撤銷退費中止')]:
            app.date_input[0].set_value(start);app.date_input[1].set_value(end);app.button[0].click().run()
            self.assertFalse(app.exception)
            frame=app.session_state['exports']['每月課程中止']
            self.assertEqual(frame['實際退費金額（未稅）'].sum(),expected)
            self.assertEqual(frame.iloc[0]['中止類型'],label)

    def test_completion_bonus_uses_original_snapshot_and_sign(self):
        data=reversed_tables();term=data['course_terminations'][0];rev=data['course_termination_reversals'][0]
        term.update(termination_type='expired',completion_bonus_eligible=True,completion_bonus_coach_id='c1',
                    fee_amount=0,refund_amount=0,recognized_amount=1400,fee_net_amount=0,refund_net_amount=0,recognized_net_amount=1333)
        rev['bonus_rule_snapshot']={'id':'old','rule_name':'虛構原規則','active':True,'effective_from':'2026-01-01','effective_to':None,'completion_rate':0.05}
        data['bonus_rules']=[dict(rev['bonus_rule_snapshot'],completion_rate=0.20)]
        data['purchases'][0]['total_amount']=4200
        app=self.app('financial',tables=data,financial_report_view='每月報表')
        for start,end,expected in [(date(2026,9,1),date(2026,9,30),100),(date(2026,10,1),date(2026,10,28),-100)]:
            app.date_input[0].set_value(start);app.date_input[1].set_value(end);app.button[0].click().run()
            self.assertFalse(app.exception)
            frame=app.session_state['exports']['每月教練結單獎金']
            self.assertEqual(frame['結單獎金'].sum(),expected)
            self.assertEqual(app.session_state['exports']['結單獎金總計']['獎金合計'].sum(),expected)
