"""全期間影子帳本：只依新規格重建及列差異，沒有任何DB寫入或回填。"""
from datetime import date
from decimal import Decimal
from financial_calculations import (FinancialDataError, decimal_value, business_date,
                                    calculate_money, build_operation_result, _sum_exact,
                                    course_net_schedule, positive_integer)


def unique_rows(records, label):
    result={}
    for r in records:
        key=r.get('id')
        if not key or key in result:raise FinancialDataError(f'{label}來源ID缺漏或重複。')
        result[key]=r
    return result


def net(gross):
    return calculate_money(gross,basis_confirmed=True).net


def allocate_payments(purchases,payments):
    """與既有付清尾差順序一致，但拒絕缺值、不修改來源。"""
    pm=unique_rows(purchases,'購課');unique_rows(payments,'收款')
    balances={};result=[]
    for row in sorted(payments,key=lambda x:(str(x.get('paid_date') or ''),str(x.get('created_at') or ''),str(x.get('id') or ''))):
        business_date(row.get('paid_date'))
        pid=row.get('purchase_id')
        if pid not in pm:raise FinancialDataError('收款對應購課缺漏。')
        total=decimal_value(pm[pid].get('total_amount'),'成交金額')
        amount=decimal_value(row.get('amount'),'收款金額')
        if total<0 or amount<0:raise FinancialDataError('成交或收款負值須另行查核，不自動分配。')
        prior,prior_net=balances.get(pid,(Decimal('0'),Decimal('0')))
        cumulative=_sum_exact((prior,amount))
        allocated=net(amount)
        if cumulative>=total and amount>0:
            overpaid=_sum_exact((cumulative,total.copy_negate()))
            allocated=_sum_exact((net(total),net(overpaid),prior_net.copy_negate()))
        if allocated<0:raise FinancialDataError('前期分配超過目標未稅，不能自動歸零。')
        balances[pid]=(cumulative,_sum_exact((prior_net,allocated)))
        result.append({**row,'net_reconstructed':allocated})
    return result


def course_ledger(snapshot):
    """保留保存銷課未稅；中止新規格另列，從不把結束狀態當成強制歸零。"""
    purchases=snapshot['purchases'];pm=unique_rows(purchases,'購課')
    payments=allocate_payments(purchases,snapshot['payments'])
    usages=snapshot['usages'];unique_rows(usages,'銷課')
    terms=snapshot['terminations'];unique_rows(terms,'中止')
    paid={};used={};terminations={};seq=set()
    for r in payments:paid.setdefault(r['purchase_id'],[]).append(r)
    for r in usages:
        if r.get('purchase_id') not in pm:raise FinancialDataError('銷課對應購課缺漏。')
        business_date(r.get('usage_date'))
        value=decimal_value(r.get('deducted_net_amount'),'保存銷課未稅')
        if value!=value.to_integral_value():raise FinancialDataError('保存銷課未稅非整元，須人工查核。')
        key=(r['purchase_id'],r.get('session_seq'))
        if key in seq:raise FinancialDataError('同購課銷課堂次重複。')
        seq.add(key);used.setdefault(r['purchase_id'],[]).append(r)
    for r in terms:
        if r.get('purchase_id') not in pm:raise FinancialDataError('中止對應購課缺漏。')
        term_day=business_date(r.get('termination_date'));pid=r['purchase_id']
        if pid in terminations:raise FinancialDataError('同購課多筆中止，須查明撤銷與重辦，不自動雙扣。')
        pn=_sum_exact(x['net_reconstructed'] for x in paid.get(pid,[]) if business_date(x['paid_date'])<=term_day)
        un=_sum_exact(decimal_value(x['deducted_net_amount']) for x in used.get(pid,[]) if business_date(x['usage_date'])<=term_day)
        base=_sum_exact((pn,un.copy_negate()))
        if base<=0:raise FinancialDataError('中止無正數實收未稅餘額，須管理員查核。')
        if any(business_date(x['usage_date'])>term_day for x in used.get(pid,[])):
            raise FinancialDataError('中止後仍有銷課，不能自動更正。')
        if r['termination_type']=='expired':
            old=net(r['recognized_amount']);fee=Decimal('0');refund=Decimal('0');expiry=base
        elif r['termination_type']=='refund':
            old=_sum_exact((net(r['fee_amount']),net(r['refund_amount'])))
            fee=net(r['fee_amount']);refund=_sum_exact((base,fee.copy_negate()));expiry=Decimal('0')
            if refund<0:raise FinancialDataError('手續費未稅超過實收未稅剩餘，不能自動負退費。')
        else:raise FinancialDataError('未知中止類型。')
        terminations[pid]={'source_id':r['id'],'old_net':old,'new_net':base,'expiry_net':expiry,'fee_net':fee,'refund_net':refund,'date':str(term_day)}
    result=[]
    for pid,p in pm.items():
        rows=used.get(pid,[])
        received=_sum_exact(x['net_reconstructed'] for x in paid.get(pid,[]))
        spent=_sum_exact(decimal_value(x['deducted_net_amount']) for x in rows)
        if len(rows)>int(p['total_sessions']):raise FinancialDataError('已銷堂數超過購課堂數。')
        completed=len(rows)==int(p['total_sessions'])
        if completed and spent!=net(p['total_amount']):raise FinancialDataError('已銷完課程未稅未勾稽，不可自動覆蓋。')
        term=terminations.get(pid)
        old=_sum_exact((received,spent.copy_negate(),(term['old_net'] if term else Decimal('0')).copy_negate()))
        standardized=_sum_exact((received,spent.copy_negate(),(term['new_net'] if term else Decimal('0')).copy_negate()))
        result.append({'purchase_id':pid,'purchase_code':p['purchase_code'],'paid_net':received,'usage_net_saved':spent,
                       'old_ledger_net':old,'standardized_net':standardized,'difference':_sum_exact((standardized,old.copy_negate())),
                       'completed':completed,'termination':term})
    return result


def project_ledger(snapshot):
    pm=unique_rows(snapshot['projects'],'專案');unique_rows(snapshot['deposits'],'儲值');unique_rows(snapshot['entries'],'專案執行')
    for r in [*snapshot['deposits'],*snapshot['entries']]:
        if r.get('project_id') not in pm:raise FinancialDataError('儲值或執行缺少對應專案。')
    result=[]
    for pid,p in pm.items():
        if p['funding_type']!='stored':continue
        deposits=[x for x in snapshot['deposits'] if x['project_id']==pid]
        entries=[x for x in snapshot['entries'] if x['project_id']==pid]
        gross=_sum_exact((_sum_exact(decimal_value(x['amount']) for x in deposits),
                          _sum_exact(decimal_value(x['line_amount']) for x in entries).copy_negate()))
        new=_sum_exact((_sum_exact(net(x['amount']) for x in deposits),
                        _sum_exact(net(x['line_amount']) for x in entries).copy_negate()))
        old=net(gross)
        result.append({'project_id':pid,'gross_balance':gross,'old_net_balance':old,'standardized_net_balance':new,'difference':_sum_exact((new,old.copy_negate())),
                       'opening_provenance_pending':any(x['transaction_type']=='opening' for x in deposits)})
    return result


def usage_alignment_plan(snapshot):
    """完整課程規格對照，輸出前後值；禁止把月度截取當成完整課程。"""
    purchases = unique_rows(snapshot['purchases'], '購課')
    usages = unique_rows(snapshot['usages'], '銷課')
    schedules = {pid: course_net_schedule(row.get('total_amount'), row.get('total_sessions'))
                 for pid, row in purchases.items()}
    seen, result = {}, []
    for uid, row in usages.items():
        pid = row.get('purchase_id')
        if pid not in purchases:
            raise FinancialDataError('銷課對應購課缺漏。')
        day = business_date(row.get('usage_date'))
        if decimal_value(row.get('deducted_amount'), '原保存銷課含稅') < 0:
            raise FinancialDataError('原保存銷課含稅為負，須查核，不自動更正。')
        seq = positive_integer(row.get('session_seq'), '銷課堂次')
        if seq in seen.setdefault(pid, set()):
            raise FinancialDataError('同購課銷課堂次重複。')
        seen[pid].add(seq)
        before = decimal_value(row.get('deducted_net_amount'), '原保存銷課未稅')
        if before < 0 or before != before.to_integral_value():
            raise FinancialDataError('原保存銷課未稅須為非負整元，須人工查核。')
        schedule = schedules[pid]
        after = schedule.amount_for(seq)
        result.append({'source_id': uid, 'purchase_id': pid,
                       'purchase_code': purchases[pid]['purchase_code'],
                       'posting_date': str(day), 'session_seq': seq,
                       'total_sessions': schedule.total_sessions,
                       'before_net': before, 'after_net': after,
                       'difference': _sum_exact((after, before.copy_negate())),
                       'reason': 'final_tail' if seq == schedule.total_sessions else 'fixed_regular',
                       'rule_version': schedule.rule_version})
    for seqs in seen.values():
        if seqs != set(range(1, len(seqs) + 1)):
            raise FinancialDataError('銷課堂次有缺號，不自動猜測堂次或改號。')
    return sorted(result, key=lambda row: (row['posting_date'], row['purchase_code'],
                                          row['session_seq'], row['source_id']))


def snapshot_at_cutoff(snapshot, cutoff):
    """先在完整歷史驗證後，再依入帳日篩選；絕不用實際服務日回放。"""
    if cutoff is None:
        return {key: list(value) if isinstance(value, list) else value
                for key, value in snapshot.items()}
    day = business_date(cutoff)
    purchases = [row for row in snapshot['purchases'] if business_date(row['purchase_date']) <= day]
    pids = {row['id'] for row in purchases}
    result = {**snapshot, 'purchases': purchases}
    for key, date_field in [('payments', 'paid_date'), ('usages', 'usage_date'),
                            ('terminations', 'termination_date')]:
        selected = [row for row in snapshot[key] if business_date(row[date_field]) <= day]
        if any(row['purchase_id'] not in pids for row in selected):
            raise FinancialDataError('截止日前存在未成交購課的事件，須查核，不能無聲漏計。')
        result[key] = selected
    return result


def standardized_course_ledger(snapshot, cutoff=None):
    """原保存帳本與完整標準化帳本分開；無 DB 寫入，保留所有原值。"""
    plan = usage_alignment_plan(snapshot)  # 必須先取得全堂次，不先裁成當月。
    proposed = {row['source_id']: row['after_net'] for row in plan}
    normalized = {**snapshot, 'usages': [
        {**row, 'deducted_net_amount': proposed[row['id']]} for row in snapshot['usages']]}
    before = course_ledger(snapshot_at_cutoff(snapshot, cutoff))
    after = {row['purchase_id']: row for row in
             course_ledger(snapshot_at_cutoff(normalized, cutoff))}
    result = []
    for saved in before:
        rebuilt = after[saved['purchase_id']]
        result.append({**saved, 'usage_net_standardized': rebuilt['usage_net_saved'],
                       'standardized_net': rebuilt['standardized_net'],
                       'difference': _sum_exact((rebuilt['standardized_net'], saved['old_ledger_net'].copy_negate())),
                       'termination_proposal': rebuilt['termination']})
    return result


def standardized_project_ledger(snapshot, cutoff=None):
    if cutoff is None:
        return project_ledger(snapshot)
    day = business_date(cutoff)
    selected = {**snapshot,
                'deposits': [row for row in snapshot['deposits'] if business_date(row['deposit_date']) <= day],
                'entries': [row for row in snapshot['entries'] if business_date(row['entry_date']) <= day]}
    return project_ledger(selected)
