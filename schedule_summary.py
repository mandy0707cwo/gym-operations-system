"""共同班表的精簡呈現；資料來源仍只接受已核准班表及安全時段投影。"""
from datetime import date
import re
import pandas as pd
from scheduling import approved_matrix,approved_data,SHIFT_LABELS,FIXED,dates_in_month


def markdown_text(value):
    # 原生st.table會解讀Markdown；姓名只能作文字，不產生連結／圖片或格式指令。
    return re.sub(r'([\\`*_{}\[\]()<>#+.!|:~=-])',r'\\\1',str(value)).replace('\n',' ').replace('\r',' ')


def summary_frame(coaches,data,month,slots):
    columns=['教練']+[f'{d.day:02d} '+ '一二三四五六日'[d.weekday()] for d in dates_in_month(month)]
    frame=pd.DataFrame(approved_matrix(coaches,data,month,slots,compact=True),columns=columns)
    frame['教練']=frame['教練'].map(markdown_text)
    for column in frame.columns[1:]:frame[column]=frame[column].map(markdown_text)
    frame.columns=pd.MultiIndex.from_tuples([('教練','')]+[(f'{d.day:02d}','週'+'一二三四五六日'[d.weekday()]) for d in dates_in_month(month)])
    return frame


def custom_time_rows(coaches,data):
    names={x['id']:x['display_name'] for x in coaches}
    return [{'日期':date.fromisoformat(x['work_date'][:10]),'教練':names.get(x['coach_id'],'未知'),
             '班別':SHIFT_LABELS[x['shift_code']],'上班':x['start_time'][:5],'下班':x['end_time'][:5]}
            for x in sorted(approved_data(data)['days'],key=lambda x:(x['work_date'],x['coach_id']))
            if x['shift_code'] not in FIXED and x.get('start_time') and x.get('end_time')]


def colored_summary_frame(coaches,data,month,slots):
    """只在原生st.table使用主題相容的Markdown底色；不污染原始資料與匯出。"""
    frame=summary_frame(coaches,data,month,slots)
    for column in frame.columns[1:]:
        frame[column]=frame[column].map(lambda value:f':blue-background[{value}]' if str(value).startswith('例假') else value)
    return frame


def unavailable_rows(coaches,slots):
    names={x['id']:x['display_name'] for x in coaches}
    return [{'日期':date.fromisoformat(x['work_date'][:10]),'教練':names.get(x['coach_id'],'未知'),
             '狀態':'不在班','開始':x['start_time'][:5],'結束':x['end_time'][:5],'時數':x['minutes']/60}
            for x in sorted(slots,key=lambda x:(x['work_date'],x['coach_id'],x['start_time']))]
