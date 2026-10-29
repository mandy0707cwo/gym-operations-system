"""月報與完整備份共用欄位／彙總；不重算稅額或獎金率。"""
from datetime import date
from decimal import Decimal
import re
import pandas as pd
from financial_calculations import decimal_value

BONUS_COLUMNS=['帳號','教練','不計成交金額','可計成交金額','獎金合計']
PENDING_COLUMNS=['帳號','教練','購買_ID','日期','待確認成交金額（未稅）','原因']


def sort_account_rows(frame):
    """報表依帳號自然升冪；空帳號置後，同帳號穩定保留原明細順序。"""
    if '帳號' not in frame.columns or frame.empty:
        return frame.copy()

    def account_key(value):
        text='' if pd.isna(value) else str(value).strip().casefold()
        parts=tuple((1,int(part)) if part.isascii() and part.isdigit() else (0,part)
                    for part in re.split(r'([0-9]+)',text))
        return (not bool(text),parts)

    # 完整備份有多個月份：先月份，再以同一規則排帳號，不跨月混排。
    accounts=frame['帳號'].tolist()
    months=frame['報表月份'].fillna('').astype(str).tolist() if '報表月份' in frame.columns else ['']*len(frame)
    order=sorted(range(len(frame)),key=lambda i:(months[i],account_key(accounts[i])))
    return frame.iloc[order].reset_index(drop=True)


def cross_month_makeup_hours(usages,purchases):
    """只統計保存為補單、且實際服務與入帳不同年月的時數；不加回執行。"""
    total=Decimal(0)
    for usage in usages:
        if usage.get('is_makeup') is not True:
            continue
        booked=date.fromisoformat(str(usage['usage_date'])[:10])
        actual=date.fromisoformat(str(usage.get('actual_usage_date') or usage['usage_date'])[:10])
        if (booked.year,booked.month)==(actual.year,actual.month):
            continue
        purchase=purchases.get(usage.get('purchase_id'))
        if purchase is None:
            raise ValueError('跨月補單缺少對應購課，停止時數彙總。')
        hours=decimal_value(purchase.get('session_hours'),'跨月補單課程時數')
        if hours<=0:
            raise ValueError('跨月補單課程時數須大於零，請查核。')
        total+=hours
    return float(total)


def _whole(value,field):
    number=decimal_value(value,field)
    if number!=number.to_integral_value():
        raise ValueError(f'{field}須沿用已計算整元，不可在彙總另行四捨五入。')
    return int(number)


def bonus_summary(coaches,details,amount_field,bonus_field,date_field):
    """資格True／False／None分別為可計／不計／待確認；絕不按姓名合併。"""
    people={p['id']:p for p in coaches}
    if len(people)!=len(coaches):
        raise ValueError('教練識別碼重複，停止獎金彙總。')
    totals={key:{'excluded':0,'eligible':0,'bonus':0} for key in people}
    pending=[]
    for row in details:
        coach_id=row.get('_coach_id')
        if coach_id not in people or '_eligible' not in row:
            raise ValueError('獎金明細缺少正確教練或資格狀態，停止彙總。')
        person=people[coach_id];amount=_whole(row.get(amount_field),amount_field)
        bonus=_whole(row.get(bonus_field),bonus_field)
        state=row['_eligible']
        if state is not True and state is not False and state is not None:
            raise ValueError('獎金資格狀態不明，不可直接列為不計。')
        if state is not True and bonus!=0:
            raise ValueError('不可計或待確認明細卻有獎金，請查核。')
        if state is None:
            pending.append({'帳號':str(person.get('username') or ''),
                '教練':person.get('display_name') or person.get('username') or '未知',
                '購買_ID':row.get('購買_ID') or '', '日期':row.get(date_field),
                '待確認成交金額（未稅）':amount,'原因':row.get('計算狀態') or '缺少適用獎金規則'})
        elif state:
            totals[coach_id]['eligible']+=amount;totals[coach_id]['bonus']+=bonus
        else:
            totals[coach_id]['excluded']+=amount
    summary=[]
    for coach_id,person in people.items():
        total=totals[coach_id]
        summary.append({'帳號':str(person.get('username') or ''),
            '教練':person.get('display_name') or person.get('username') or '未知',
            '不計成交金額':total['excluded'],'可計成交金額':total['eligible'],'獎金合計':total['bonus']})
    return sort_account_rows(pd.DataFrame(summary,columns=BONUS_COLUMNS)),sort_account_rows(pd.DataFrame(pending,columns=PENDING_COLUMNS))
