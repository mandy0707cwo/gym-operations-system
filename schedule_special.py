"""統一特殊假別的唯讀投影；不覆蓋原班表，也不推算薪資／法定假日。"""
from copy import deepcopy
from datetime import date,timedelta
from scheduling import first_day,dates_in_month,STATES,REVIEWERS
from schedule_leave import minute

SPECIAL_KINDS={'public_off':'統一公休','typhoon':'颱風天','spring':'春節','banquet':'尾牙','other':'其他特殊假別'}


def normalize_special(month,payload):
    if not isinstance(payload,dict):raise ValueError('特殊假別資料格式不正確')
    start=date.fromisoformat(str(payload.get('date_from')))
    end=date.fromisoformat(str(payload.get('date_to')))
    if start>end or start.replace(day=1).isoformat()!=month or end.replace(day=1).isoformat()!=month:
        raise ValueError('日期起迄須在目前月份，且開始不可晚於結束')
    kind=payload.get('kind');label=str(payload.get('label') or '').strip()
    if kind not in SPECIAL_KINDS or not label or len(label)>100:raise ValueError('請填寫有效假別及100字內名稱')
    units=payload.get('deduct_units')
    if type(units) is not int or units not in (0,1,2):raise ValueError('請明確指定該日排休扣額度0、0.5或1天')
    a,b=payload.get('start_time'),payload.get('end_time')
    if a is not None or b is not None:raise ValueError('本版特殊假別僅支援整日休')
    reason=str(payload.get('reason') or '').strip()
    if not reason or len(reason)>1000:raise ValueError('請填寫1000字內設定／修改原因')
    return {'date_from':start.isoformat(),'date_to':end.isoformat(),'kind':kind,'label':label,
            'start_time':a,'end_time':b,'deduct_units':units,'reason':reason}


def active_specials(record,month):
    result={}
    for row in record.get('days',[]):
        if row.get('state')!='active':continue
        d=str(row['work_date'])[:10]
        if first_day(d).isoformat()!=month or d in result:raise ValueError('特殊假別日期重複或跨月')
        if type(row.get('deduct_units')) is not int or row['deduct_units'] not in (0,1,2):raise ValueError('特殊假別扣額度不明')
        a,b=row.get('start_time'),row.get('end_time')
        if a is not None or b is not None:raise ValueError('本版特殊假別僅支援整日休')
        result[d]=row
    return result


def special_projection(data,specials,for_headcount=False):
    """全日改為顯示公休；部分時段另由可用時段聯集扣除。原資料保留。"""
    out=deepcopy(data)
    for row in out['days']:
        event=specials.get(str(row['work_date'])[:10])
        if event:
            row['special_deduct_units']=event['deduct_units']
            row['special_label']=event['label']
            row['special_full_off']=True
            if not for_headcount:
                row.update(shift_code='public_off',start_time=None,end_time=None)
    return out


def combined_slots(data,slots,specials):
    """將特殊假別與既有請假裁切並聯集，不重複扣工時；不傳私人假別原因。"""
    approved={x['coach_id'] for x in data['months'] if x['state']=='approved'}
    result=[]
    for row in data['days']:
        if row['coach_id'] not in approved or not row.get('start_time') or not row.get('end_time'):continue
        a,b=minute(row['start_time']),minute(row['end_time'])
        intervals=[(minute(x['start_time']),minute(x['end_time'])) for x in slots
                   if x['coach_id']==row['coach_id'] and x['work_date']==row['work_date']]
        event=specials.get(row['work_date'])
        if event:intervals.append((minute(event['start_time']),minute(event['end_time'])) if event.get('start_time') else (a,b))
        merged=[]
        for x,y in sorted((max(a,x),min(b,y)) for x,y in intervals if x<b and y>a):
            if merged and x<=merged[-1][1]:merged[-1][1]=max(y,merged[-1][1])
            else:merged.append([x,y])
        for x,y in merged:
            result.append({'coach_id':row['coach_id'],'work_date':row['work_date'],
                'start_time':f'{x//60:02d}:{x%60:02d}','end_time':f'{y//60:02d}:{y%60:02d}','minutes':y-x})
    return result


def progress_rows(me,data,month,usernames):
    if me.get('role') not in REVIEWERS:raise ValueError('僅主管或管理者可查看全體排休完成狀態')
    expected={d.isoformat() for d in dates_in_month(month)}
    records={x['coach_id']:x for x in data['months'] if x['month_start']==month}
    result=[]
    for coach in data['coaches']:
        if not coach.get('active',True):continue
        rows=[x for x in data['days'] if x['coach_id']==coach['id'] and x['work_date'] in expected]
        filled={x['work_date'] for x in rows}
        if len(filled)!=len(rows):raise ValueError('班表日期重複，無法判定完成狀態')
        m=records.get(coach['id'],{})
        completed=bool(m.get('coach_locked') or m.get('finalized_at')) and filled==expected
        result.append({'帳號':str(usernames.get(coach['id']) or '').upper(),'教練':coach['display_name'],
            '排休進度':'已完成' if completed else '未完成','已填日期':f'{len(filled)}/{len(expected)}',
            '尚未填寫（天）':len(expected-filled),'班表狀態':STATES[m['state']] if m else '未開始',
            '確認時間':m.get('finalized_at') or ('歷史已確認，時間未追溯' if m.get('coach_locked') else '')})
    return result
