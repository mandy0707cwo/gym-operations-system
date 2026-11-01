"""營運管理唯讀計算：依來源日期、逐筆未稅與課程筆數，不更動交易。"""
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from financial_calculations import calculate_money, decimal_value, positive_integer
from finance_reporting import usage_net
from termination_reporting import effective_terminations


def day(value):
    return date.fromisoformat(str(value))


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError('開始日期不可晚於結束日期。')

    @property
    def label(self):
        return f'{self.start:%Y-%m-%d} ～ {self.end:%Y-%m-%d}'

    def includes(self, value):
        return self.start <= day(value) <= self.end


def shift_month(value, offset):
    number = value.year * 12 + value.month - 1 + offset
    year, month = divmod(number, 12)
    month += 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def calendar_period(kind, year, month=1, quarter=1):
    if kind == '月':
        start = date(year, month, 1)
        return Period(start, date(year, month, monthrange(year, month)[1]))
    if kind == '季':
        if quarter not in (1, 2, 3, 4):
            raise ValueError('季度須為1至4。')
        start = date(year, (quarter - 1) * 3 + 1, 1)
        return Period(start, shift_month(start, 3) - timedelta(days=1))
    if kind == '年':
        return Period(date(year, 1, 1), date(year, 12, 31))
    raise ValueError('不支援的統計期間。')


def comparison_periods(kind, selected, as_of):
    """未結束期間按相同日曆進度比較；自訂區間取緊接前一等天數區間。"""
    if selected.start > as_of:
        raise ValueError('選取期間尚未開始，沒有實際營運結果。')
    current = Period(selected.start, min(selected.end, as_of))
    if kind == '自訂':
        count = (current.end - current.start).days + 1
        previous = Period(current.start - timedelta(days=count), current.start - timedelta(days=1))
    else:
        offset = {'月': 1, '季': 3, '年': 12}[kind]
        previous_start = shift_month(selected.start, -offset)
        previous_end = (shift_month(selected.start, 0) - timedelta(days=1))
        if current.end < selected.end:
            previous_end = min(previous_end, shift_month(current.end, -offset))
        previous = Period(previous_start, previous_end)
    last_year = Period(shift_month(current.start, -12), shift_month(current.end, -12))
    return current, previous, last_year


def unique_rows(records, label):
    result = {}
    for row in records:
        key = row.get('id')
        if not key or key in result:
            raise ValueError(f'{label}識別碼缺漏或重複，停止顯示合計。')
        result[key] = row
    return result


def completion_dates(purchases, usages, terminations):
    """讀完整銷課歷史，以第N筆有效銷課入帳日認定全部堂數銷完。"""
    by_purchase = unique_rows(purchases, '購課')
    unique_rows(usages, '銷課')
    grouped = defaultdict(list)
    for row in usages:
        if row.get('purchase_id') not in by_purchase:
            raise ValueError('銷課缺少對應購課，停止顯示合計。')
        grouped[row['purchase_id']].append(row)
    termination_groups = defaultdict(list)
    for row in terminations:
        termination_groups[row['purchase_id']].append(row)
    output = {}
    for purchase_id, records in grouped.items():
        purchase = by_purchase[purchase_id]
        total = positive_integer(purchase.get('total_sessions'), '購課堂數')
        if len(records) > total:
            raise ValueError('銷課筆數超過購課堂數，請先查核。')
        if len(records) < total:
            continue
        ordered = sorted(records, key=lambda row: (day(row['usage_date']), str(row.get('created_at') or ''), row['id']))
        completed = day(ordered[-1]['usage_date'])
        if not effective_terminations(termination_groups[purchase_id], completed):
            # 不用今天的狀態覆蓋過去；已中止但未銷完不會進入分母。
            output[purchase_id] = completed
    return output


def course_net(row):
    gross = row.get('total_amount')
    rebuilt = calculate_money(gross, basis_confirmed=True)
    if rebuilt.gross < 0:
        raise ValueError('購課成交金額不可為負數。')
    saved = calculate_money(gross, stored_net=row.get('total_net_amount'),
                            stored_rule_version=row.get('calculation_rule_version'))
    if saved.net != rebuilt.net:
        raise ValueError('保存購課未稅與正式計算中心不符，請先查核。')
    return int(saved.net)


class OperationsMetrics:
    def __init__(self, sources):
        self.sources = sources
        for name in ('purchases', 'session_usages', 'trial_items'):
            unique_rows(sources[name], name)
        if any(row.get('purchase_kind') not in ('first', 'renewal') for row in sources['purchases']):
            raise ValueError('購課類型缺漏或不支援，不能判定首次購買／續約。')
        if 'completed_counts' in sources:
            # 正式入口僅接收受控RPC的日期與數量；不下載中止或退款明細。
            natural = completion_dates(sources['purchases'], sources['session_usages'], [])
            maximum = defaultdict(int)
            for completed in natural.values():
                maximum[completed] += 1
            self.completed_counts = {}
            for row in sources['completed_counts']:
                completed = day(row['completed_date'])
                number = decimal_value(row.get('completed_courses'), '完成課程數')
                if completed in self.completed_counts or number < 0 or number != number.to_integral_value():
                    raise ValueError('完成課程統計重複或數量格式不符。')
                if number > maximum[completed]:
                    raise ValueError('完成統計與可讀購課／銷課範圍不一致，請重新查詢。')
                self.completed_counts[completed] = int(number)
        else:
            # 僅供離線舊備份及虛構資料的純計算，不是正式讀取器的降級路徑。
            unique_rows(sources.get('course_terminations', []), 'course_terminations')
            natural = completion_dates(sources['purchases'], sources['session_usages'], sources.get('course_terminations', []))
            self.completed_counts = defaultdict(int)
            for completed in natural.values():
                self.completed_counts[completed] += 1

    def totals(self, period):
        purchases = [row for row in self.sources['purchases'] if period.includes(row['purchase_date'])]
        usages = [row for row in self.sources['session_usages'] if period.includes(row['usage_date'])]
        trials = [row for row in self.sources['trial_items'] if period.includes(row['entry_date'])]
        paid_trials = 0
        for row in trials:
            amount = decimal_value(row.get('amount'), '體驗含稅金額')
            if amount < 0:
                raise ValueError('體驗金額為負數，請先查核。')
            paid_trials += amount > 0
        first = sum(row.get('purchase_kind') == 'first' for row in purchases)
        renewals = sum(row.get('purchase_kind') == 'renewal' for row in purchases)
        completed = sum(number for value, number in self.completed_counts.items() if period.start <= value <= period.end)
        return {
            'sales_net': sum(course_net(row) for row in purchases),
            'sales_sessions': sum(positive_integer(row.get('total_sessions'), '購課堂數') for row in purchases),
            'usage_net': sum(usage_net(row) for row in usages),
            'usage_sessions': len(usages),
            'trial_visits': len(trials), 'paid_trial_visits': paid_trials,
            'first_orders': first, 'renewal_orders': renewals, 'completed_courses': completed,
            'trial_rate': Decimal(first) / paid_trials if paid_trials else None,
            'renewal_rate': Decimal(renewals) / completed if completed else None,
        }


ANNUAL_ROWS = (
    ('每月成交金額（未稅）', 'sales_net', 'money'),
    ('每月成交堂數', 'sales_sessions', 'count'),
    ('每月銷課金額（未稅）', 'usage_net', 'money'),
    ('每月銷課堂數', 'usage_sessions', 'count'),
    ('每月體驗人次', 'trial_visits', 'count'),
    ('每月體驗成交率', 'trial_rate', 'rate'),
    ('每月續約率', 'renewal_rate', 'rate'),
)


def annual_totals(engine, year, as_of):
    rows = []
    for month in range(1, 13):
        selected = calendar_period('月', year, month)
        totals = None if selected.start > as_of else engine.totals(Period(selected.start, min(selected.end, as_of)))
        rows.append({'month': month, 'totals': totals})
    return rows


def change_rate(current, previous):
    if previous == 0:
        return None
    return (Decimal(current) - Decimal(previous)) / Decimal(previous)


def display_value(value, kind):
    if value is None:
        return '—'
    if kind == 'money':
        return f'$ {value:,.0f}'
    if kind == 'rate':
        return f'{value:.1%}'
    return f'{value:,}'
