"""正式範圍回歸：使用工作區暫存目錄，不連線正式資料庫。"""
import os
from pathlib import Path
import tempfile
import sys

ROOT=Path(__file__).resolve().parents[1]
TEST_TEMP=ROOT/"output"/"test-temp-v1.13.11"
TEST_TEMP.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(TEST_TEMP)
os.environ["TEMP"]=str(TEST_TEMP)
os.environ["TMP"]=str(TEST_TEMP)
sys.path.insert(0,str(ROOT/"tests"))

from verify_v1_13_8 import main
import verify_v1_13_8 as regression
regression.MODULES=(*regression.MODULES,"test_termination_records",
                   "test_course_defaults","test_navigation_platforms")

if __name__=="__main__":
    raise SystemExit(main())
