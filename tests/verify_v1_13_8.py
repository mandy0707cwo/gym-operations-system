"""執行正式範圍回歸測試；排除已暫停活動方案，不連線 Supabase。"""
import importlib
import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
MODULES = (
    'test_purchase_codes', 'test_project_queries', 'test_project_queries_ui',
    'test_financial_backup', 'test_general_usage_query',
    'test_payment_net_allocation', 'test_purchase_installment_ui',
)

def main():
    suite = unittest.TestSuite()
    try:
        for name in MODULES:
            module = importlib.import_module(name)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            for test_name, test in inspect.getmembers(module, inspect.isfunction):
                if test_name.startswith('test_'):
                    suite.addTest(unittest.FunctionTestCase(test))
    except ImportError as exc:
        print(f'缺少測試套件：{exc}。請先安裝 requirements.txt。', file=sys.stderr)
        return 2
    return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
