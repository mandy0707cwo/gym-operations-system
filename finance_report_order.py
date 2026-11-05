"""財務報表輸出順序：只重排列，不變更日期、金額、欄位或原始輸入。"""
from datetime import date, datetime
import pandas as pd

# 優先依交易日期；只有到期清單沒有交易日期時，才依期限排序。
DATE_COLUMNS = ('日期', '成交／預收日期', '成交日期', '銷課日期', '執行日期',
                '儲值日期', '課程完成日期', '有效期限', '有效日期', '課程期限', '效期')


def sort_report_dates(frame):
    column = next((name for name in DATE_COLUMNS if name in frame.columns), None)
    if column is None or frame.empty:
        return frame.copy(deep=True)

    def key(value):
        # 合計與無日期列保留在最後，不讓合計混入明細；非法日期不可默默略過。
        if pd.isna(value) or (isinstance(value, str) and value.strip() in ('', '合計', '總計')):
            return (1, date.min)
        if isinstance(value, datetime):
            return (0, value.date())
        if isinstance(value, date):
            return (0, value)
        if isinstance(value, str):
            try:
                return (0, date.fromisoformat(value.strip()))
            except ValueError:
                pass
        raise ValueError(f'財務報表「{column}」含無效日期，請先查核來源資料。')

    keys = [key(value) for value in frame[column].tolist()]
    order = sorted(range(len(frame)), key=lambda index: keys[index])
    return frame.iloc[order].reset_index(drop=True)


def report_frame(*args, **kwargs):
    """畫面與下載共同使用同一份已排序資料；無日期的彙總維持原順序。"""
    return sort_report_dates(pd.DataFrame(*args, **kwargs))
