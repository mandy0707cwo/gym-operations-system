"""獨立請假時段；只保存分鐘，不推算薪資、休息扣時或達成率。"""
from datetime import date, datetime, time
import re
from scheduling import REVIEWERS, STATES
from schedule_allowance import allowance_totals, days_text

LEAVE_TYPES={'annual':'特休','sick':'病假','personal':'事假','other':'其他'}


def minute(value):
    if isinstance(value,time):value=value.isoformat()
    if not isinstance(value,str) or not re.fullmatch(r'\d{2}:\d{2}(:00)?',value):
        raise ValueError('請填寫分鐘精度的有效時間；本版不跨日')
    try:t=time.fromisoformat(value)
    except ValueError as exc:raise ValueError('時間無效') from exc
    return t.hour*60+t.minute


def leave_payload(month,payload):
    if not isinstance(payload,dict):raise ValueError('請假內容無效')
    raw=payload.get('work_date')
    if isinstance(raw,date) and not isinstance(raw,datetime):raw=raw.isoformat()
    if not isinstance(raw,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):raise ValueError('請假日期無效')
    d=date.fromisoformat(raw)
    if d.replace(day=1).isoformat()!=month:raise ValueError('請假日期不在目前月份')
    kind=payload.get('leave_kind')
    if kind not in LEAVE_TYPES:raise ValueError('請選擇有效假別')
    start,end=minute(payload.get('start_time')),minute(payload.get('end_time'))
    if start>=end:raise ValueError('請假開始須早於結束；跨日請分開登錄')
    reason=payload.get('reason')
    if not isinstance(reason,str) or not reason.strip() or len(reason.strip())>1000:
        raise ValueError('請填寫1000字內的登錄／修改原因')
    return {'work_date':raw,'leave_kind':kind,'start_time':f'{start//60:02d}:{start%60:02d}',
            'end_time':f'{end//60:02d}:{end%60:02d}','reason':reason.strip(),'minutes':end-start}


def validate_leave(data,records,coach,month,payload,exclude_id=None):
    record=next((x for x in data['months'] if x['coach_id']==coach and x['month_start']==month),None)
    if not record or record['state']!='approved':raise ValueError('請先核准本月班表，再登錄請假')
    day=next((x for x in data['days'] if x['coach_id']==coach and x['work_date']==payload['work_date']),None)
    if not day or not day.get('start_time') or not day.get('end_time'):
        raise ValueError('此日沒有上班時段，不可在已排休時段重複登錄請假')
    start,end=minute(payload['start_time']),minute(payload['end_time'])
    if start<minute(day['start_time']) or end>minute(day['end_time']):raise ValueError('請假須完整落在當日已核准上班時段內')
    for row in records:
        if row.get('state')=='active' and row['id']!=exclude_id and row['coach_id']==coach and row['work_date']==payload['work_date']:
            if start<minute(row['end_time']) and minute(row['start_time'])<end:raise ValueError('請假時段重疊，不可重複登錄')


def guard_schedule_leave(row,records):
    """後續改班也不能把既有有效請假移到休假或班外。"""
    for leave in records:
        if leave['state']=='active' and leave['coach_id']==row['coach_id'] and leave['work_date']==row['work_date']:
            if not row.get('start_time') or not row.get('end_time') or minute(leave['start_time'])<minute(row['start_time']) or minute(leave['end_time'])>minute(row['end_time']):
                raise ValueError('此日已有有效請假，請先更正或作廢請假，再變更班表')


def availability(records,data):
    approved={(x['coach_id'],x['month_start']) for x in data['months'] if x['state']=='approved'}
    return [{k:x[k] for k in ('coach_id','work_date','start_time','end_time','minutes')}
            for x in records if x['state']=='active' and (x['coach_id'],x['month_start']) in approved]


def allowance_overview(record,data,month):
    """不把未填班表當已排休0天；每位教練明列資料審核狀態。"""
    months={x['coach_id']:x for x in data['months']}
    result=[]
    for coach in data['coaches']:
        c=coach['id'];m=months.get(c);days=[x for x in data['days'] if x['coach_id']==c]
        total=allowance_totals(record,days,month,c) if record and m and days else None
        result.append({'教練':coach['display_name'],'班表狀態':STATES[m['state']] if m else '尚未建立',
            '已核定可排休（天）':record['total_units']/2 if record else None,
            '已排休（天）':total['used_units']/2 if total else None,
            '剩餘額度（天）':total['remaining_units']/2 if total else None})
    return result
