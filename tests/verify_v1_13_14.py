"""v1.13.14 隔離回歸，不使用正式帳號、不連線正式資料庫。"""
import logging
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP = ROOT / "output" / "test-temp-v1.13.14"
TEST_TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEST_TEMP)
os.environ["TEMP"] = os.environ["TMP"] = str(TEST_TEMP)
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import verify_v1_13_8 as regression
regression.MODULES = (*regression.MODULES, "test_termination_records", "test_course_defaults",
                      "test_navigation_platforms", "test_ui_text", "test_confirmed_queries",
                      "test_query_views_v1_13_14")
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)
# 隔離測試直接操作session_state會有已知bare-mode警告；保留錯誤及測試失敗輸出。
logging.disable(logging.WARNING)

if __name__ == "__main__":
    raise SystemExit(regression.main())
