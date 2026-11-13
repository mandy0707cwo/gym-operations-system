"""中止的未稅預覽：沿用已入帳的未稅與現行手續費尾差。"""
from decimal import Decimal, ROUND_HALF_UP

from financial_calculations import calculate_money, decimal_value


def preview_termination(remaining_gross, remaining_net, kind, charge_fee):
    gross = decimal_value(remaining_gross, '退費前含稅餘額')
    net = decimal_value(remaining_net, '退費前未稅餘額')
    if kind not in ('expired', 'refund'):
        raise ValueError('請選擇中止類型。')
    if gross <= 0 or net < 0 or net != net.to_integral_value():
        raise ValueError('實收扣除銷課後的餘額不符中止條件，請先查核。')
    gross_fee = (gross * Decimal('0.20')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if kind == 'refund' and charge_fee else Decimal(0)
    fee = calculate_money(gross_fee, basis_confirmed=True).net
    if fee > net:
        raise ValueError('手續費超過未稅餘額，請先查核。')
    return net, fee, net - fee if kind == 'refund' else Decimal(0)


def render_preview(st, amounts, kind):
    balance, fee, refund = amounts
    if kind == 'refund':
        a, b, c = st.columns(3)
        a.metric('退費前剩餘金額（未稅）', f'$ {balance:,.0f}')
        b.metric('手續費（未稅）', f'$ {fee:,.0f}')
        c.metric('實際退費金額（未稅）', f'$ {refund:,.0f}')
    else:
        st.metric('退費前剩餘金額（未稅）', f'$ {balance:,.0f}')
