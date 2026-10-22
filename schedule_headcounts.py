"""核准排班人數：以整數分鐘扣除不在班區間，不推算出勤或預約。"""
from datetime import date
from scheduling import approved_data,dates_in_month,SHIFT_LABELS,FIXED,OFF
from schedule_leave import minute

GROUPS={'A':'A班','B':'B班','C':'C班','total':'合計'}


def summary_group(code,start=None,end=None):
    """只改顯示分組；重疊時段不猜原A／B，不改原始班別。"""
    if code=='other':return 'C'
    if code=='half_off':
        if start is None or end is None:raise ValueError('半日休缺少上班時段')
        matches=[key for key,(a,b) in FIXED.items() if minute(a)<=start<end<=minute(b)]
        return matches[0] if len(matches)==1 else 'C'
    if code not in ('A','B','C'):raise ValueError('無法分類的上班班別')
    return code


def query_window(mode='整日',start=None,end=None):
    if mode=='整日':return None
    if mode!='指定時段':raise ValueError('請選擇整日或指定時段')
    a,b=minute(start),minute(end)
    if a>=b:raise ValueError('查詢開始須早於結束；不支援跨日')
    return (a,b)


def difference(start,end,intervals):
    """裁切、聯集後求剩餘區段，重複／相接的請假不重扣。"""
    merged=[]
    for a,b in sorted((max(start,a),min(end,b)) for a,b in intervals if a<end and b>start):
        if not merged or a>merged[-1][1]:merged.append([a,b])
        else:merged[-1][1]=max(merged[-1][1],b)
    cursor=start;remaining=[]
    for a,b in merged:
        if cursor<a:remaining.append((cursor,a))
        cursor=max(cursor,b)
    if cursor<end:remaining.append((cursor,end))
    return remaining


def hm(value):return f'{value//60:02d}:{value%60:02d}'


def headcounts(coaches,data,month,slots,window=None):
    allowed_dates={x.isoformat() for x in dates_in_month(month)}
    if window is not None and (not isinstance(window,(tuple,list)) or len(window)!=2 or
        any(type(x) is not int for x in window) or not 0<=window[0]<window[1]<1440):
        raise ValueError('查詢時段無效')
    approved=approved_data(data)
    months={}
    for row in approved['months']:
        if row['month_start']!=month:continue
        if row['coach_id'] in months:raise ValueError('核准班表月份重複，請查核')
        months[row['coach_id']]=row
    if not months:raise ValueError('本月尚無已核准班表，不以0人代替')
    days={}
    for row in approved['days']:
        if row['month_start']!=month or row['coach_id'] not in months:continue
        key=(row['coach_id'],row['work_date'])
        if row['work_date'] not in allowed_dates or key in days:raise ValueError('核准班表日期有重複或不在本月')
        if row['shift_code'] not in SHIFT_LABELS:raise ValueError('核准班別無效')
        days[key]=row
    if len(days)!=len(months)*len(allowed_dates):raise ValueError('核准班表缺少日期，請查核，不以0人代替')
    leave={}
    for slot in slots:
        if slot['coach_id'] not in months:continue
        if slot['work_date'] not in allowed_dates:raise ValueError('不在班日期不在目前月份')
        a,b=minute(slot['start_time']),minute(slot['end_time'])
        if a>=b:raise ValueError('不在班時段無效')
        leave.setdefault((slot['coach_id'],slot['work_date']),[]).append((a,b))
    names={x['id']:x['display_name'] for x in coaches}
    staff={}
    for (coach,day),row in days.items():
        source=row['shift_code']
        if source in OFF:continue
        start,end=row.get('start_time'),row.get('end_time')
        if (start is None)!=(end is None):raise ValueError('核准上班時段不完整')
        if start is None:
            if source!='other':raise ValueError('核准班別缺少上班時段')
            group=summary_group(source)
            item={'available':None,'partial':True,'coach':coach,'name':names.get(coach,months[coach]['coach_name']),
                'shift':SHIFT_LABELS[source],'scheduled':'未填時段','remaining':'無法判斷','status':'待確認：未填上班時段'}
        else:
            a,b=minute(start),minute(end)
            if a>=b:raise ValueError('核准上班時段無效')
            if source in FIXED and (a,b)!=tuple(minute(x) for x in FIXED[source]):raise ValueError('核准A／B班時段不符固定班別')
            group=summary_group(source,a,b)
            if window and not (a<window[1] and b>window[0]):continue
            remain=difference(a,b,leave.get((coach,day),[]))
            full=sum(y-x for x,y in remain)==b-a
            if window:
                available=any(x<=window[0] and y>=window[1] for x,y in remain)
                partial=bool(remain) and not available
            else:
                available=bool(remain)
                partial=available and not full
            status=('查詢全時段可用' if window else '整個班段在班') if available and not partial else (
                '部分時段不在班' if not window and available else '未涵蓋查詢全時段' if window and remain else '整個班段不在班')
            item={'available':available,'partial':partial or source in ('half_off','other'),'coach':coach,'name':names.get(coach,months[coach]['coach_name']),
                'shift':SHIFT_LABELS[source],'scheduled':f'{hm(a)}–{hm(b)}',
                'remaining':'、'.join(f'{hm(x)}–{hm(y)}' for x,y in remain) or '無','status':status}
        staff.setdefault((day,group),[]).append(item)
        staff.setdefault((day,'total'),[]).append(item)
    headers=[{'date':x.isoformat(),'day':f'{x.day:02d}','weekday':'一二三四五六日'[x.weekday()]} for x in dates_in_month(month)]
    rows=[]
    for group,label in GROUPS.items():
        cells=[]
        for header in headers:
            values=staff.get((header['date'],group),[])
            original=len(values);unknown=any(x['available'] is None for x in values)
            available=None if unknown else sum(bool(x['available']) for x in values)
            partial=any(x['partial'] for x in values)
            text=f'{available if available is not None else "—"}/{original}'+('＊' if partial else '')
            cells.append({'date':header['date'],'text':text,'original':original,
                          'shortage':available is not None and available<original})
        rows.append({'group':group,'label':label,'cells':cells})
    return {'headers':headers,'rows':rows,'staff':staff,'window':window,'month':month}


def headcount_details(result,selection):
    if not isinstance(selection,dict) or selection.get('group') not in GROUPS or selection.get('date') not in {x['date'] for x in result['headers']}:
        raise ValueError('請選擇本月有效的日期與班別')
    return [{'日期':date.fromisoformat(selection['date']),'教練':x['name'],'班別':x['shift'],
             '原排上班時段':x['scheduled'],'扣除不在班後時段':x['remaining'],'狀況':x['status']}
            for x in sorted(result['staff'].get((selection['date'],selection['group']),[]),key=lambda x:(x['name'],x['coach']))]
