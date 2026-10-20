"""銷課畫面的含稅實收餘額；資料庫仍是最後核准依據。"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('收款或銷課金額缺漏，請先查核') from exc
    if not amount.is_finite():
        raise ValueError('收款或銷課金額不是有效數字')
    return amount


def usage_funds(balance, payments):
    """使用現有完整課程餘額 view，避免漏算其他教練執行的堂次。"""
    result = dict(balance)
    total = money(balance['total_amount'])
    contract_remaining = money(balance['remaining_amount'])
    total_sessions = int(balance['total_sessions'])
    remaining_sessions = int(balance['remaining_sessions'])
    if total_sessions <= 0 or not 0 < remaining_sessions <= total_sessions:
        raise ValueError('課程堂數異常，請先查核')
    received = sum((money(p['amount']) for p in payments
                    if p['purchase_id'] == balance['purchase_id']), Decimal('0'))
    used = total - contract_remaining
    next_amount = (contract_remaining if remaining_sessions == 1 else
                   (total / total_sessions).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    if used < 0 or next_amount < 0:
        raise ValueError('既有銷課金額異常，請先查核')
    result.update(received_amount=received, actual_prepaid_balance=received-used,
                  next_usage_amount=next_amount,
                  usage_shortfall=max(next_amount-(received-used), Decimal('0')))
    return result
