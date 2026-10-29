"""共同彙總的精確金額、資格分類及跨月時數測試。"""
from copy import deepcopy
import unittest
from monthly_report_layout import BONUS_COLUMNS,PENDING_COLUMNS,bonus_summary,cross_month_makeup_hours


class LayoutTests(unittest.TestCase):
    def test_bonus_three_states_signed_offsets_zero_rate_and_duplicate_names(self):
        coaches=[{'id':'a','username':'SMC001','display_name':'同名'},
                 {'id':'b','username':'SMC002','display_name':'同名'}]
        details=[{'_coach_id':coach,'_eligible':state,'amount':amount,'bonus':bonus,
                  '購買_ID':str(i),'day':'2026-09-02','計算狀態':'查無適用的獎金規則' if state is None else '已計算'}
                 for i,(coach,state,amount,bonus) in enumerate([
                    ('a',True,1000,50),('a',False,2000,0),('a',None,3000,0),
                    ('a',True,-100,-5),('a',True,400,0),('b',True,500,25)])]
        before=deepcopy(details)
        summary,pending=bonus_summary(coaches,details,'amount','bonus','day')
        self.assertEqual(summary.columns.tolist(),BONUS_COLUMNS)
        self.assertEqual(pending.columns.tolist(),PENDING_COLUMNS)
        self.assertEqual(summary.iloc[0].tolist(),['SMC001','同名',2000,1300,45])
        self.assertEqual(summary.iloc[1].tolist(),['SMC002','同名',0,500,25])
        self.assertEqual(pending['待確認成交金額（未稅）'].sum(),3000)
        self.assertEqual(summary['不計成交金額'].sum()+summary['可計成交金額'].sum()+pending['待確認成交金額（未稅）'].sum(),sum(x['amount'] for x in details))
        self.assertEqual(details,before)

    def test_empty_sources_still_have_five_columns(self):
        summary,pending=bonus_summary([],[],'amount','bonus','day')
        self.assertEqual(summary.columns.tolist(),BONUS_COLUMNS)
        self.assertEqual(pending.columns.tolist(),PENDING_COLUMNS)

    def test_malformed_rows_fail_instead_of_silent_classification(self):
        coaches=[{'id':'a'}]
        valid={'_coach_id':'a','_eligible':True,'amount':100,'bonus':5}
        for change in ({'_coach_id':'unknown'},{'_eligible':'False'}, {'amount':100.1},
                       {'_eligible':None,'bonus':5},{'bonus':None}):
            with self.assertRaises(ValueError):bonus_summary(coaches,[dict(valid,**change)],'amount','bonus','day')
        with self.assertRaises(ValueError):bonus_summary(coaches+coaches,[],'amount','bonus','day')

    def test_makeup_cross_year_and_same_month_and_saved_flag(self):
        records=[{'purchase_id':'p','usage_date':'2026-09-01','actual_usage_date':day,'is_makeup':flag}
                 for day,flag in [('2026-08-31',True),('2026-09-01',True),('2026-08-01',False),('2026-08-01',None)]]
        records.append({'purchase_id':'q','usage_date':'2026-01-02','actual_usage_date':'2025-12-31','is_makeup':True})
        before=deepcopy(records)
        self.assertEqual(cross_month_makeup_hours(records,{'p':{'session_hours':1.5},'q':{'session_hours':0.5}}),2)
        self.assertEqual(records,before)

    def test_cross_month_missing_or_invalid_hours_is_not_guessed(self):
        row={'purchase_id':'p','usage_date':'2026-09-01','actual_usage_date':'2026-08-31','is_makeup':True}
        for purchases in ({},{'p':{}},{'p':{'session_hours':0}},{'p':{'session_hours':-1}}):
            with self.assertRaises(ValueError):cross_month_makeup_hours([row],purchases)


if __name__=='__main__':unittest.main()
