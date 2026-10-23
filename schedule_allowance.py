"""排休額度純規則；只計算管理員明確核定的假日，不推定官方假日。"""
from datetime import date,datetime
from scheduling import first_day,dates_in_month,SHIFT_LABELS

DEDUCT_CODES=('full_off','half_off','weekend','public_off')
DEDUCT_UNITS={'full_off':2,'half_off':1,'weekend':0,'public_off':2}  # 單位為半天，使用者已確認。


def exact_date(value):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    if not isinstance(value,str) or len(value)!=10:raise ValueError('請填寫完整日期yyyy-mm-dd')
    return date.fromisoformat(value)


def normalize_allowance(month,payload):
    start=exact_date(month)
    if start!=first_day(start):raise ValueError('月份須為月初日期')
    if not isinstance(payload,dict):raise ValueError('額度資料格式不正確')
    entries=payload.get('holidays');units=payload.get('deduct_units')
    if not isinstance(entries,list) or len(entries)>31:raise ValueError('假日明細須為最多31筆的清單')
    if not isinstance(units,dict) or set(units)!=set(DEDUCT_CODES):raise ValueError('請明確設定各休假班別如何扣額度')
    if any(type(v) is not int or v not in (0,1,2) for v in units.values()):raise ValueError('扣算單位須為0、0.5或1天')
    if units!=DEDUCT_UNITS:raise ValueError('扣算方式須符合已確認規則：整日休1天、半日休0.5天、公休1天，其餘不扣')
    seen_original=set();seen_observed=set();holidays=[]
    for row in entries:
        if not isinstance(row,dict):raise ValueError('假日明細格式不正確')
        name=str(row.get('name') or '').strip()
        if not name or len(name)>100:raise ValueError('假日名稱必填且不可超過100字')
        original=exact_date(row.get('original_date'));observed=exact_date(row.get('observed_date'))
        if first_day(observed)!=start:raise ValueError('計入日期須在所選月份；跨月補假歸實際補假月份')
        if original.weekday()>=5:
            if observed==original or observed.weekday()>=5:raise ValueError('週末重疊的國定假日只填平日補假，不再計入原假日')
        elif observed!=original:raise ValueError('非週末國定假日的計入日期應與原假日相同')
        if original in seen_original or observed in seen_observed:raise ValueError('原假日或計入日期重複，請合併核對')
        seen_original.add(original);seen_observed.add(observed)
        holidays.append({'name':name,'original_date':original.isoformat(),'observed_date':observed.isoformat()})
    note=str(payload.get('note') or '').strip()
    if len(note)>1000:raise ValueError('額度說明不可超過1000字')
    saturdays=sum(d.weekday()==5 for d in dates_in_month(start))
    return {'month_start':start.isoformat(),'saturday_days':saturdays,'holiday_days':len(holidays),
            'total_units':(saturdays+len(holidays))*2,'holidays':sorted(holidays,key=lambda x:x['observed_date']),
            'deduct_units':dict(units),'note':note}


def allowance_totals(record,days,month,coach):
    if record is None:return None
    normalized=normalize_allowance(month,record)
    # 來源回覆若已不一致，不拿錯誤的總額繼續顯示。
    if record.get('total_units')!=normalized['total_units']:raise ValueError('月額度來源合計不一致，請管理員查核')
    used=0;unknown=[];seen=set()
    for row in days:
        if row['coach_id']!=coach:continue
        d=exact_date(row['work_date'])
        if first_day(d)!=first_day(month) or d in seen:raise ValueError('排班日期跨月或重複')
        seen.add(d);code=row['shift_code']
        if code not in SHIFT_LABELS:raise ValueError('排班含未知班別')
        units=row.get('special_deduct_units',normalized['deduct_units'].get(code,0))
        if type(units) is not int or units not in (0,1,2):raise ValueError('特殊假別扣額度不正確')
        used+=units
    return {'total_units':normalized['total_units'],'used_units':used,
            'remaining_units':normalized['total_units']-used,'unclassified_days':unknown}


def days_text(units):
    return str(units//2) if units%2==0 else f'{units/2:g}'
