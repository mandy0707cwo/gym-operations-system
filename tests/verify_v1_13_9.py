"""v1.13.9 正式範圍回歸；不連線正式資料庫。"""
from verify_v1_13_8 import main
import verify_v1_13_8 as regression
regression.MODULES=(*regression.MODULES,"test_termination_records")
if __name__=="__main__":
    raise SystemExit(main())
