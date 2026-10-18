"""正式報表共用介面：缺失不補零，金額先逐筆分配再合計。"""
from decimal import Decimal, ROUND_HALF_UP
from financial_calculations import calculate_money, decimal_value, _sum_exact
from financial_reconciliation import allocate_payments


def display_money(value, tax_mode):
    gross = decimal_value(value)
    if tax_mode == '未稅':
        return int(calculate_money(gross, basis_confirmed=True).net)
    if tax_mode != '含稅':
        raise ValueError('不支援的稅別。')
    return int(gross.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def payment_allocations(purchases, payments):
    result = allocate_payments(purchases, payments)
    for row in result:
        row['_net_amount'] = int(row['net_reconstructed'])
        saved = row.get('net_amount')
        if saved is not None and decimal_value(saved) != row['net_reconstructed']:
            raise ValueError('保存收款未稅與計算中心不同，請重新查詢並由管理員查核。')
    return result


def usage_net(row):
    value = decimal_value(row.get('deducted_net_amount'), '保存銷課未稅')
    if value < 0 or value != value.to_integral_value():
        raise ValueError('保存銷課未稅須為非負整元。')
    return int(value)


def termination_money(row, field, tax_mode):
    if tax_mode == '含稅':
        return decimal_value(row.get(field), field)
    key = {'remaining_amount':'remaining_net_amount', 'recognized_amount':'recognized_net_amount',
           'fee_amount':'fee_net_amount', 'refund_amount':'refund_net_amount'}[field]
    return int(decimal_value(row.get(key), '保存中止未稅'))


def ledger_balance(received, used, termination=None, tax_mode='未稅'):
    deductions = []
    if termination:
        fields = ('recognized_amount',) if termination['termination_type'] == 'expired' else ('fee_amount', 'refund_amount')
        deductions = [decimal_value(termination_money(termination, key, tax_mode)) for key in fields]
    return _sum_exact((decimal_value(received), decimal_value(used).copy_negate(),
                       _sum_exact(deductions).copy_negate()))


def event_net_total(records, field):
    return int(_sum_exact(Decimal(event_net(row,field)) for row in records))


def event_net(row, field):
    rebuilt=calculate_money(row.get(field),basis_confirmed=True)
    if 'net_amount' not in row:
        return int(rebuilt.net)  # 僅供未含保存欄位的離線來源／舊備份重建。
    stored=calculate_money(row.get(field),stored_net=row['net_amount'],
                           stored_rule_version=row.get('calculation_rule_version'))
    if stored.net!=rebuilt.net:
        raise ValueError('保存未稅與共同規格不同，須管理員查核，不顯示部分合計。')
    return int(stored.net)
