"""教練績效：只彙總保存未稅，不平均比率、不將金額與工時相加。"""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

TARGET_WORK_RATIO = Decimal('0.80')
FACTS = frozenset(('sales_net', 'sales_sessions', 'first_orders', 'renewal_orders',
    'usage_net', 'usage_sessions', 'usage_hours', 'trial_visits', 'paid_trial_visits',
    'trial_hours', 'single_hours', 'project_hours', 'oneoff_net', 'cancelled_sessions',
    'completed_courses', 'refund_courses', 'refund_net'))
MONEY = frozenset(('sales_net', 'usage_net', 'oneoff_net', 'refund_net'))
COUNTS = FACTS - MONEY - {'usage_hours', 'trial_hours', 'single_hours', 'project_hours'}


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('績效來源含缺少或無效的數值。') from exc
    if not result.is_finite():
        raise ValueError('績效來源含非有限數值。')
    return result


def ratio(a, b):
    return a / b if b > 0 else None


def month_periods(start, end):
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise ValueError('請提供完整、正確的日期區間。')
    cursor = start.replace(day=1)
    while cursor <= end:
        last = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
        yield max(cursor, start), min(last, end)
        if last >= end:
            break
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def account_sort(row):
    parts = re.split(r'(\d+)', str(row.get('username') or '').lower())
    return tuple((1, int(p)) if p.isdigit() else (0, p) for p in parts), str(row['id'])


def minutes_from_hours(value):
    raw = number(value) * 60
    nearest = raw.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    if raw < 0 or abs(raw - nearest) > Decimal('0.00000001'):
        raise ValueError('上班時數須為非負數，且能換算為整分鐘（例如 160、160.5、160.25）。')
    return int(nearest)


def hours_changes(month, coaches, saved, edited):
    """空白是未提供，不當成0；僅傳送真正修改的列，附原始版本。"""
    allowed = {r['id'] for r in coaches}
    previous = {r['coach_id']: r for r in saved}
    seen, output = set(), []
    for row in edited:
        coach = row['coach_id']
        if coach not in allowed or coach in seen:
            raise ValueError('教練資料無效或重複，請重新載入。')
        seen.add(coach)
        value = row['hours']
        old = previous.get(coach)
        if value is None or str(value) in ('nan', '<NA>'):
            if old is not None:
                raise ValueError('已保存工時不可清空；沒有上班請明確輸入0。')
            continue
        minutes = minutes_from_hours(value)
        if minutes > monthrange(month.year, month.month)[1] * 1440:
            raise ValueError('工時不可超過當月全部日曆時數。')
        if old is None or minutes != old['minutes']:
            output.append({'coach_id': coach, 'minutes': minutes, 'revision': old['revision'] if old else 0})
    if seen != allowed:
        raise ValueError('工時表列數不完整，請重新載入。')
    return sorted(output, key=lambda r: r['coach_id'])


class CoachPerformance:
    def __init__(self, payload, start, end):
        if not isinstance(payload, dict) or payload.get('schema_version') != 49 or payload.get('start') != str(start) or payload.get('end') != str(end):
            raise ValueError('績效回傳版本或期間不同，請重新查詢。')
        self.start, self.end = start, end
        self.coaches = sorted(payload['coaches'], key=account_sort)
        self.ids = {r['id'] for r in self.coaches}
        if len(self.ids) != len(self.coaches):
            raise ValueError('教練資料重複。')
        self.facts, seen = [], set()
        for row in payload['facts']:
            day, coach, field = date.fromisoformat(row['day']), row['coach_id'], row['metric']
            value = number(row['value'])
            identity = (coach, day, field)
            if coach not in self.ids or field not in FACTS or not start <= day <= end or identity in seen:
                raise ValueError('績效明細含重複、未知教練或超出查詢期間。')
            if (field in MONEY | COUNTS and value != value.to_integral_value()) or (field not in {'refund_courses', 'refund_net'} and value < 0):
                raise ValueError('績效金額／次數或時數不合理。')
            seen.add(identity)
            self.facts.append((coach, day, field, value))
        self.cohorts = {}
        for row in payload['cohorts']:
            key = (row['coach_id'], row['start_date'], row['end_date'])
            a, b = number(row['opening_members']), number(row['retained_members'])
            if key in self.cohorts or key[0] not in self.ids or a < b or b < 0 or a != int(a) or b != int(b):
                raise ValueError('會員維持率來源不一致。')
            self.cohorts[key] = (a, b)
        self.hours = {}
        for row in payload['hours']:
            key = (row['coach_id'], row['month'])
            minutes = number(row['minutes'])
            month = date.fromisoformat(row['month'])
            if key in self.hours or key[0] not in self.ids or month.day != 1 or minutes < 0 or minutes != int(minutes) or minutes > monthrange(month.year, month.month)[1] * 1440:
                raise ValueError('每月工時來源不一致。')
            self.hours[key] = minutes / 60

    def totals(self, coach, start=None, end=None):
        start, end = start or self.start, end or self.end
        if coach not in self.ids or not self.start <= start <= end <= self.end:
            raise ValueError('請在已查詢範圍內統計。')
        r = {field: Decimal(0) for field in FACTS}
        for c, day, field, value in self.facts:
            if c == coach and start <= day <= end:
                r[field] += value
        r.update(average_sale=ratio(r['sales_net'], r['sales_sessions']),
                 trial_rate=ratio(r['first_orders'], r['paid_trial_visits']),
                 renewal_rate=ratio(r['renewal_orders'], r['completed_courses']),
                 cancellation_rate=ratio(r['cancelled_sessions'], r['usage_sessions'] + r['cancelled_sessions']))
        r['execution_hours'] = sum(r[k] for k in ('usage_hours', 'trial_hours', 'single_hours', 'project_hours'))
        opening, retained = self.cohorts.get((coach, str(start), str(end)), (Decimal(0), Decimal(0)))
        r.update(opening_members=opening, retained_members=retained, retention_rate=ratio(retained, opening))
        # 月工時無法精準分攤部分月份，不能按日期比例猜算。
        periods = list(month_periods(start, end))
        full = all(a.day == 1 and b.day == monthrange(b.year, b.month)[1] for a, b in periods)
        missing = [f'{a:%Y-%m}' for a, _ in periods if (coach, str(a.replace(day=1))) not in self.hours]
        r['work_hours'] = None
        r['achievement_rate'] = None
        if not full:
            r['hours_status'] = '非完整月份，不分攤月工時'
        elif missing:
            r['hours_status'] = '未填工時：' + '、'.join(missing)
        else:
            r['work_hours'] = sum(self.hours[(coach, str(a))] for a, _ in periods)
            r['achievement_rate'] = ratio(r['execution_hours'], r['work_hours'] * TARGET_WORK_RATIO)
            r['hours_status'] = '上班時數為0，無法計算' if r['work_hours'] == 0 else '已提供月工時'
        return r

    def monthly(self, coach):
        return [{'月份': f'{a:%Y-%m}', **self.totals(coach, a, b)} for a, b in month_periods(self.start, self.end)]
