"""中止與撤銷的共同日期規則；不連線、不刪除原交易、不重新換算稅額。"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo('Asia/Taipei')
MONEY_FIELDS = ('remaining_amount', 'recognized_amount', 'fee_amount', 'refund_amount',
                'remaining_net_amount', 'recognized_net_amount', 'fee_net_amount', 'refund_net_amount')


def reversal_date(record):
    value = record.get('reversed_at')
    if not value:
        return None
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('撤銷時間缺少時區，停止計算。')
    return stamp.astimezone(TAIPEI).date().isoformat()


def effective_terminations(records, cutoff):
    """截止日仍有效的中止；撤銷前的歷史不被今天的狀態覆蓋。"""
    end = date.fromisoformat(str(cutoff)[:10]).isoformat()
    result = []
    for row in records:
        day = date.fromisoformat(str(row['termination_date'])[:10]).isoformat()
        undone = reversal_date(row)
        if undone and undone < day:
            raise ValueError('撤銷日期早於原中止，停止計算。')
        if day <= end and (not undone or undone > end):
            result.append(row)
    ids = [x['purchase_id'] for x in result]
    if len(ids) != len(set(ids)):
        raise ValueError('同一購課有多筆有效中止，停止計算。')
    return result


def termination_sign(row):
    return -1 if row.get('is_reversal') is True else 1


def termination_label(row):
    label = '逾期中止' if row['termination_type'] == 'expired' else '退費中止'
    return ('撤銷' if termination_sign(row) < 0 else '') + label


def termination_events(records, reversals, cutoff):
    """供完整備份報表使用；與 SQL 事件 view 相同，沖回留在撤銷月份。"""
    end = date.fromisoformat(str(cutoff)[:10]).isoformat()
    by_id = {x['termination_id']: x for x in reversals}
    if len(by_id) != len(reversals):
        raise ValueError('中止撤銷記錄重複，停止計算。')
    output = []
    for row in records:
        day = str(row['termination_date'])[:10]
        rev = by_id.get(row['id'])
        original = dict(deepcopy(row), is_reversal=False, original_termination_date=day,
                        original_termination_id=row['id'], snapshot_available=bool(rev),
                        purchase_snapshot=(rev or {}).get('original_purchase'),
                        bonus_rule_snapshot=(rev or {}).get('bonus_rule_snapshot'))
        if day <= end:
            output.append(original)
        undone = reversal_date(row)
        if bool(undone) != bool(rev):
            raise ValueError('中止與撤銷記錄不完整，停止計算。')
        if not rev:
            continue
        if str(rev['reversal_date'])[:10] != undone or rev['purchase_id'] != row['purchase_id']:
            raise ValueError('中止撤銷關聯或日期不符，停止計算。')
        if undone < day:
            raise ValueError('撤銷日期早於原中止，停止計算。')
        if undone <= end:
            item = dict(original, id=rev['id'], termination_date=undone, is_reversal=True,
                        created_by=rev['created_by'], created_at=rev['created_at'], reason=rev['reason'])
            for field in MONEY_FIELDS:
                if row.get(field) is None:
                    raise ValueError('中止金額缺值，不可產生不完整沖回。')
                item[field] = -Decimal(str(row[field]))
            item['remaining_sessions'] = -int(row['remaining_sessions'])
            output.append(item)
    return sorted(output, key=lambda x: (str(x['termination_date']), str(x['id'])))
