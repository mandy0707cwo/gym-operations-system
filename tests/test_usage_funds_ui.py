import unittest
from streamlit.testing.v1 import AppTest
from test_usage_idempotency_ui import SCRIPT
from test_purchase_installment_ui import ROOT


class UsageFundsUITests(unittest.TestCase):
    def app(self,role='coach',paid=3150,fail=False):
        script=SCRIPT.replace('usage_page(me)', '''
st.session_state.db['purchase_payments'][0]['amount']=st.session_state['funds_paid']
if st.session_state.get('funds_read_fail'):
 original_execute=Query.execute
 def fail_payments(self):
  if self.table=='purchase_payments': raise RuntimeError('模擬收款讀取失敗')
  return original_execute(self)
 Query.execute=fail_payments
usage_page(me)''')
        app=AppTest.from_string('APP_PATH='+repr(str(ROOT/'app.py'))+'\n'+script,default_timeout=30)
        app.session_state['role']=role
        app.session_state['funds_paid']=paid
        app.session_state['funds_read_fail']=fail
        app.run()
        next(x for x in app.selectbox if x.label=='會員名稱').set_value('虛構客戶').run()
        self.assertFalse(app.exception)
        return app

    def button(self,app): return next(x for x in app.button if x.label=='確認扣除 1 堂')

    def test_coach_short_zero_negative_blocked(self):
        for paid in (3149.99,2100,1050):
            with self.subTest(paid=paid):
                app=self.app(paid=paid)
                self.assertTrue(self.button(app).disabled)
                self.assertTrue(app.warning)
                self.assertEqual(len(app.session_state['writes']),0)
                self.assertTrue(any('實際預收餘額(含稅)' in x for x in next(x for x in app.selectbox if x.label=='選擇課程').options))

    def test_exact_enough_enabled_and_submit(self):
        app=self.app()
        self.assertFalse(self.button(app).disabled)
        self.assertTrue(any('1,050.00' in x.value for x in app.caption))
        self.button(app).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['writes']),1)

    def test_other_roles_existing_permission_but_warn(self):
        for role in ('admin','manager','shared_coach'):
            with self.subTest(role=role):
                app=self.app(role=role,paid=1050)
                self.assertFalse(self.button(app).disabled)
                self.assertTrue(app.warning)

    def test_payment_read_failure_never_defaults_to_zero_or_submits(self):
        app=self.app(fail=True)
        self.assertTrue(any('暫停銷課' in x.value for x in app.error))
        self.assertFalse(any(x.label=='確認扣除 1 堂' for x in app.button))
        self.assertEqual(len(app.session_state['writes']),0)

    def test_after_payment_refresh_enables(self):
        app=self.app(paid=1050)
        self.assertTrue(self.button(app).disabled)
        app.session_state['funds_paid']=3150
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(self.button(app).disabled)
