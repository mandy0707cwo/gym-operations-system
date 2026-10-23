"""排班純規則：不連資料庫，不涉及薪資、銷課或獎金。"""
import calendar
from datetime import date, time

SHIFT_LABELS={'A':'A班','B':'B班','C':'C班','full_off':'整日休','half_off':'半日休',
              'weekend':'週末','regular_off':'例假','public_off':'公休','other':'其他'}
FIXED={'A':('09:00','18:00'),'B':('12:00','21:00')}
OFF=frozenset(('full_off','weekend','regular_off','public_off'))
STATES={'draft':'草稿','submitted':'待審','approved':'已核准','returned':'退回'}
ROLES=frozenset(('coach','manager','admin'))
REVIEWERS=frozenset(('manager','admin'))
EDITABLE_SHIFTS=tuple(x for x in SHIFT_LABELS if x!='weekend')


def first_day(value):
    d=date.fromisoformat(str(value)[:10]) if not isinstance(value,date) else value
    return d.replace(day=1)


def dates_in_month(value):
    d=first_day(value)
    return [d.replace(day=n) for n in range(1,calendar.monthrange(d.year,d.month)[1]+1)]


def day_payload(work_date,shift,start=None,end=None,note=''):
    if shift not in SHIFT_LABELS:raise ValueError('請選擇有效班別')
    d=date.fromisoformat(str(work_date)[:10]) if not isinstance(work_date,date) else work_date
    note=str(note or '').strip()
    if len(note)>1000:raise ValueError('備註不可超過1000字')
    if shift in FIXED:start,end=FIXED[shift]
    elif shift in OFF:start=end=None
    if shift=='other' and not note:raise ValueError('其他班別請填寫說明')
    if (start is None)!=(end is None):raise ValueError('上班時段須同時填寫開始與結束')
    if shift in ('C','half_off') and (start is None or end is None):raise ValueError('此班別須填寫上班時段')
    if start is not None:
        try:
            a=time.fromisoformat(str(start));b=time.fromisoformat(str(end))
        except ValueError as exc:raise ValueError('請填寫有效時間') from exc
        if a>=b or a.second or b.second or a.microsecond or b.microsecond:
            raise ValueError('上班時間須早於下班時間，且以分鐘填寫；本版不跨日')
        start,end=a.strftime('%H:%M'),b.strftime('%H:%M')
    return {'work_date':d.isoformat(),'shift_code':shift,'start_time':start,'end_time':end,'note':note}


def fill_empty(month,base,existing):
    if base not in FIXED:raise ValueError('請先設定A班或B班')
    saved={str(x['work_date'])[:10] for x in existing}
    return [day_payload(d,'regular_off' if d.weekday()==6 else base)
            for d in dates_in_month(month) if d.isoformat() not in saved]


def display_day(d,saved):
    """未儲存週日只顯示預設提示，不冒充已儲存或已核准。"""
    if saved:return saved
    if d.weekday()==6:return dict(day_payload(d,'regular_off'),preview=True)
    return {'work_date':d.isoformat(),'shift_code':None,'preview':True}


def can_edit(role,actor,target,state,finalized_at=None):
    return role in REVIEWERS or (role=='coach' and actor==target and state in ('draft','returned') and not finalized_at)


def approved_data(data):
    """共同總表只使用已核准月份，絕不拿週日預覽補成核准資料。"""
    months=[x for x in data['months'] if x['state']=='approved']
    keys={(x['coach_id'],x['month_start']) for x in months}
    return {'months':months,'days':[x for x in data['days']
            if (x['coach_id'],x['month_start']) in keys]}


def approved_matrix(coaches,data,month,unavailable=(),compact=False):
    approved=approved_data(data)
    names={x['id']:x['display_name'] for x in coaches}
    days={(x['coach_id'],x['work_date'][:10]):x for x in approved['days']}
    rows=[]
    for item in sorted(approved['months'],key=lambda x:names.get(x['coach_id'],x['coach_name'])):
        coach=item['coach_id'];row={'教練':names.get(coach,item['coach_name'])}
        for d in dates_in_month(month):
            saved=days.get((coach,d.isoformat()))
            label=''
            if saved:
                code=saved['shift_code'];label=saved.get('special_label') or SHIFT_LABELS[code]
                if not compact and code not in FIXED and saved.get('start_time'):
                    label+=' '+str(saved['start_time'])[:5]+'–'+str(saved['end_time'])[:5]
            marked=False
            for leave in unavailable:
                if leave['coach_id']==coach and leave['work_date']==d.isoformat():
                    if compact:
                        if not marked:label+='＊';marked=True
                    else:label+=f'｜不在班 {leave["start_time"][:5]}–{leave["end_time"][:5]}'
            row[f'{d.day:02d} '+ '一二三四五六日'[d.weekday()]]=label
        rows.append(row)
    return rows


def export_rows(coaches,months,days):
    """僅匯出已儲存資料；文字移除Excel公式執行風險。"""
    names={x['id']:x['display_name'] for x in coaches}
    status={x['coach_id']:x for x in months}
    def safe(value):
        text=str(value or '')
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text
    return [{'日期':date.fromisoformat(x['work_date'][:10]),
             '教練':safe(names.get(x['coach_id'],status.get(x['coach_id'],{}).get('coach_name','未知'))),
             '班別':safe(x.get('special_label') or SHIFT_LABELS[x['shift_code']]),'上班時段':str(x.get('start_time') or '')[:5],
             '下班時段':str(x.get('end_time') or '')[:5],
             '審核狀態':STATES[status[x['coach_id']]['state']],'備註':safe(x.get('note'))}
            for x in sorted(days,key=lambda r:(r['work_date'],r['coach_id']))]
