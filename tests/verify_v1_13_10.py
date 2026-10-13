"""v1.13.10 正式範圍回歸；不連正式資料庫。"""
from verify_v1_13_8 import main
import verify_v1_13_8 as regression
regression.MODULES=(*regression.MODULES,"test_termination_records","test_course_defaults")
if __name__=="__main__":
    raise SystemExit(main())
