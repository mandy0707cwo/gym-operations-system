"""實際 Operation 介面的成功收據、下一筆與回覆遺失恢復。"""
from datetime import date
import unittest
from streamlit.testing.v1 import AppTest
import test_purchase_installment_ui as purchase_ui
SCRIPT,ROOT=purchase_ui.SCRIPT,purchase_ui.ROOT


class OperationUITests(unittest.TestCase):
    widget = purchase_ui.PurchaseUITests.widget
    fill_purchase = purchase_ui.PurchaseUITests.fill_purchase
    clean = purchase_ui.PurchaseUITests.clean

    def app(self):
        app = AppTest.from_string("APP_PATH=" + repr(str(ROOT / 'app.py')) + '\n' + SCRIPT, default_timeout=30)
        app.run()
        self.clean(app)
        return app

    def test_success_shows_original_receipt_until_explicit_next(self):
        app = self.app()
        self.fill_purchase(app)
        token = app.query_params['op_purchase'][0]
        self.widget(app,'button','確認並建立購買紀錄').click().run()
        self.clean(app)
        self.assertTrue(any(x.label=='開始下一筆購課' for x in app.button))
        self.assertFalse(any(x.label=='確認並建立購買紀錄' for x in app.button))
        self.assertEqual(len(app.session_state['writes']),1)
        app.run()
        self.assertEqual(len(app.session_state['writes']),1)
        self.assertEqual(app.query_params['op_purchase'][0],token)
        self.widget(app,'button','開始下一筆購課').click().run()
        self.clean(app)
        self.assertNotEqual(app.query_params['op_purchase'][0],token)
        self.assertIsNone(self.widget(app,'number_input','成交總金額').value)

    def test_unknown_reply_does_not_resend_on_rerun_and_recovers(self):
        app = self.app()
        self.fill_purchase(app)
        app.session_state['incomplete_rpc'] = True
        self.widget(app,'button','確認並建立購買紀錄').click().run()
        self.clean(app)
        self.assertEqual(app.session_state['_operation_purchase']['state'],'uncertain')
        self.assertEqual(len(app.session_state['writes']),1)
        app.run()
        self.assertEqual(len(app.session_state['writes']),1)
        self.widget(app,'button','查核原操作結果').click().run()
        self.clean(app)
        self.assertEqual(app.session_state['_operation_purchase']['state'],'completed')
        self.assertEqual(len(app.session_state['writes']),1)

    def test_failure_cancel_then_new_form_without_new_transaction(self):
        app = self.app()
        self.fill_purchase(app)
        app.session_state['fail_table'] = 'purchase_payments'
        self.widget(app,'button','確認並建立購買紀錄').click().run()
        self.clean(app)
        self.widget(app,'button','取消未完成操作').click().run()
        self.clean(app)
        self.assertEqual(app.session_state['_operation_purchase']['state'],'cancelled')
        self.widget(app,'button','重新填寫').click().run()
        self.clean(app)
        self.assertIsNone(self.widget(app,'number_input','成交總金額').value)
        self.assertEqual(app.session_state['writes'],[])


if __name__=='__main__':
    unittest.main()
