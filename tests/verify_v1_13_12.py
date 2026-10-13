"""v1.13.12 正式範圍回歸，不連線正式資料庫。"""
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
TEST_TEMP=ROOT/"output"/"test-temp-v1.13.12"
TEST_TEMP.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(TEST_TEMP)
os.environ["TEMP"]=str(TEST_TEMP)
os.environ["TMP"]=str(TEST_TEMP)
sys.path.insert(0,str(ROOT/"tests"))

from verify_v1_13_8 import main
import verify_v1_13_8 as regression
regression.MODULES=(*regression.MODULES,"test_termination_records",
                   "test_course_defaults","test_navigation_platforms","test_ui_text")

if __name__=="__main__":
    raise SystemExit(main())
