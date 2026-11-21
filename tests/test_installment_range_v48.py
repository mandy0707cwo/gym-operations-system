"""分期入帳期間只用虛構資料，無正式 DB 連線或寫入。"""
from datetime import date
from io import BytesIO
import unittest

from openpyxl import load_workbook
from course_query_views import business_today
import test_online_finance as base


def tables():
    purchase = dict(member_id='m',coach_id='c1',course_name='虛構課程',
                    purchase_date='2026-10-01',total_amount=2100,total_sessions=3,
                    payment_plan='installment',installment_count=3)
    purchases=[dict(purchase,id=f'p{i}',purchase_code=f'TEST-0{i}') for i in range(1,8)]
    purchases[4]['payment_plan']='full'
    purchases[6]['purchase_date']='2026-10-20'
    rows=[('p1',1,'2026-10-01',700),('p1',2,'2026-10-31',700),('p1',3,'2026-11-01',700),
          ('p2',2,'2026-10-30',700),('p3',2,'2026-11-02',700),('p4',1,'2026-11-01',700),
          ('p5',2,'2026-11-01',700),('p6',2,'2026-11-01',700),
          ('p7',1,'2026-10-20',1050),('p7',2,'2026-11-01',1050)]
    payments=[dict(id=f'r{i}',purchase_id=p,installment_no=n,paid_date=d,amount=a,
                   payment_kind='supplement' if p=='p6' else 'installment')
              for i,(p,n,d,a) in enumerate(rows)]
    usages=[dict(id=f'u{i}',purchase_id='p1',usage_date='2026-11-01') for i in range(3)]
    return {'purchases':purchases,'purchase_payments':payments,'session_usages':usages,
            'course_terminations':[],'course_termination_reversals':[],
            'members':[dict(id='m',member_name='虛構會員')],
            'profiles':[dict(id='c1',display_name='虛構教練',role='coach',active=True)]}


class InstallmentPeriodTests(unittest.TestCase):
    app=base.FinancialScreenTests.app

    def open(self,**state):
        return self.app('general',general_query_main_tab='每日預收',
                        general_prepaid_mode='今日分期入帳',tables=tables(),**state)

    def query(self,app,start=date(2026,10,31),end=date(2026,11,1)):
        app.date_input(key='daily_installment_start').set_value(start)
        app.date_input(key='daily_installment_end').set_value(end)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        return app

    def test_defaults_to_taiwan_today_and_waits_for_query(self):
        app=self.open()
        self.assertEqual([x.value for x in app.date_input],[business_today()]*2)
        self.assertEqual(app.session_state['reads'],['profiles'])
        self.assertFalse(app.dataframe);self.assertFalse(app.get('download_button'))

    def test_cross_month_boundaries_no_first_full_supplement_or_double_purchase(self):
        app=self.query(self.open())
        self.assertFalse(app.error)
        df=app.dataframe[0].value
        self.assertEqual(df['購買_ID'].tolist(),['TEST-01','TEST-07'])
        self.assertEqual(df['已收金額（含稅）'].tolist(),[2100,2100])
        self.assertEqual(df['已收金額（未稅）'].tolist(),[2000,2000])
        self.assertEqual([x.value for x in app.metric],['$ 2,333','$ 2,450'])
        self.assertEqual([x.label for x in app.metric],['期間分期入帳（未稅）','期間分期入帳（含稅）'])
        self.assertEqual(df['狀態'].tolist(),['已完成','進行中'])

    def test_single_day_cutoff_excludes_later_payment_and_usage(self):
        app=self.query(self.open(),end=date(2026,10,31))
        df=app.dataframe[0].value
        self.assertEqual(df['購買_ID'].tolist(),['TEST-01'])
        self.assertEqual(df['已收金額（含稅）'].tolist(),[1400])
        self.assertEqual(df['已收金額（未稅）'].tolist(),[1334])
        self.assertEqual(df['分期狀態'].tolist(),['未付清'])
        self.assertEqual(df['狀態'].tolist(),['進行中'])
        self.assertEqual([x.value for x in app.metric],['$ 667','$ 700'])

    def test_changing_period_invalidates_snapshot_and_download(self):
        app=self.query(self.open());reads=len(app.session_state['reads'])
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['reads'][reads:],['profiles'])
        app.date_input(key='daily_installment_start').set_value(date(2026,11,1)).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.dataframe);self.assertFalse(app.get('download_button'))
        self.assertTrue(any('請設定條件' in x.value for x in app.info))
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual([x.value for x in app.metric],['$ 1,666','$ 1,750'])

    def test_bad_or_empty_dates_do_not_read_transactions(self):
        for start,end in [(date(2026,11,2),date(2026,11,1)),(None,date(2026,11,1)),(date(2026,10,31),None)]:
            with self.subTest(start=start,end=end):
                app=self.query(self.open(),start,end)
                self.assertTrue(app.error)
                self.assertEqual(set(app.session_state['reads']),{'profiles'})
                self.assertFalse(app.dataframe);self.assertFalse(app.get('download_button'))

    def test_empty_result_zeros_and_clears_old_download(self):
        app=self.query(self.open())
        self.assertTrue(app.get('download_button'))
        self.query(app,date(2026,12,1),date(2026,12,31))
        self.assertFalse(app.error);self.assertFalse(app.dataframe)
        self.assertFalse(app.get('download_button'))
        self.assertEqual([x.value for x in app.metric],['$ 0','$ 0'])

    def test_screen_and_excel_match_and_filename_contains_period(self):
        app=self.query(self.open());df=app.dataframe[0].value
        self.assertFalse(df.attrs)
        self.assertTrue(df.equals(app.session_state['exports']['分期入帳']))
        book=load_workbook(BytesIO(app.session_state['export_bytes']),data_only=True)
        ws=book['分期入帳']; headers=[c.value for c in ws[1]]
        self.assertEqual(headers,list(df.columns))
        for column in ('購買_ID','成交日期','已收金額（含稅）','已收金額（未稅）'):
            exported=[ws.cell(i,headers.index(column)+1).value for i in (2,3)]
            if column=='成交日期': exported=[value.date().isoformat() for value in exported]
            self.assertEqual(exported,df[column].tolist())
        self.assertEqual(app.get('download_button')[0].proto.label,'下載 Excel')
        self.assertIsNotNone(app.get('download_button')[0].key)
        self.assertIn('2026-10-31_2026-11-01',app.get('download_button')[0].key)

    def test_other_roles_cannot_use_admin_query(self):
        for role in ('coach','shared_coach','manager'):
            app=self.open(role=role)
            self.assertTrue(app.warning)
            self.assertEqual(app.session_state['reads'],[])
            self.assertFalse(app.button)
