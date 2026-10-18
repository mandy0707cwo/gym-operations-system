"""全期間副本試算：逐筆前後值、月份及餘額，無網路或資料庫寫入。"""
import argparse
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from financial_calculations import build_operation_result, ENGINE_VERSION, RULE_VERSION, _sum_exact, business_date
from financial_reconciliation import (standardized_course_ledger, standardized_project_ledger,
                                      usage_alignment_plan, allocate_payments, net)


def build_history_proposal(data, cutoff=None, *, restore_test_deferred=False):
    cutoff_day = business_date(cutoff) if cutoff else None
    groups = defaultdict(list)
    for row in data['operations']:
        if cutoff_day is None or business_date(row['entry_date']) <= cutoff_day:
            groups[(row['kind'], row['entry_date'][:7])].append(row)
    operations, operation_lines = [], []
    for (kind, month), records in sorted(groups.items()):
        report = build_operation_result(records)
        if report.unknown_count or report.missing_id_count:
            raise ValueError('體驗或單堂來源不完整，停止整份試算。')
        operations.append({'kind': kind, 'month': month, 'count': len(report.lines),
                           'gross': report.gross_total, 'net_standardized': report.net_total})
        operation_lines.extend({'source_id': line.source_id, 'kind': kind,
                                'posting_date': str(line.entry_date), 'gross': line.money.gross,
                                'net_reconstructed': line.money.net,
                                'origin': line.money.origin, 'rule_version': line.money.rule_version}
                               for line in report.lines)
    plan = usage_alignment_plan(data)
    selected = [row for row in plan if cutoff_day is None or business_date(row['posting_date']) <= cutoff_day]
    monthly = defaultdict(list)
    for row in selected:
        monthly[row['posting_date'][:7]].append(row)
    monthly_usage = [
        {'month': month, 'count': len(rows), 'changed_count': sum(bool(row['difference']) for row in rows),
         'before_net': _sum_exact(row['before_net'] for row in rows),
         'after_net': _sum_exact(row['after_net'] for row in rows),
         'difference': _sum_exact(row['difference'] for row in rows)}
        for month, rows in sorted(monthly.items())]
    payments = allocate_payments(data['purchases'], data['payments'])
    monthly = defaultdict(list)
    for row in payments:
        if cutoff_day is None or business_date(row['paid_date']) <= cutoff_day:
            monthly[row['paid_date'][:7]].append(row)
    monthly_payments = [
        {'month': month, 'count': len(rows),
         'gross': _sum_exact(Decimal(str(row['amount'])) for row in rows),
         'net_standardized': _sum_exact(row['net_reconstructed'] for row in rows)}
        for month, rows in sorted(monthly.items())]
    courses = standardized_course_ledger(data, cutoff)
    projects = standardized_project_ledger(data, cutoff)
    project_events = []
    for key, field, date_field in [('deposits', 'amount', 'deposit_date'),
                                   ('entries', 'line_amount', 'entry_date')]:
        for row in data[key]:
            if cutoff_day is None or business_date(row[date_field]) <= cutoff_day:
                project_events.append({**row, 'event_kind': key, 'origin': 'reconstructed',
                                       'net_reconstructed': net(row[field]), 'rule_version': RULE_VERSION})
    by_purchase = {row['purchase_id']: row for row in courses}
    term_changes = []
    for row in data['terminations']:
        if cutoff_day is not None and business_date(row['termination_date']) > cutoff_day:
            continue
        course = by_purchase[row['purchase_id']]
        proposed = course['termination_proposal']
        before_expiry = net(row['recognized_amount']) if row['termination_type'] == 'expired' else Decimal(0)
        before_fee = net(row['fee_amount']) if row['termination_type'] == 'refund' else Decimal(0)
        before_refund = net(row['refund_amount']) if row['termination_type'] == 'refund' else Decimal(0)
        term_changes.append({'source_id': row['id'], 'purchase_code': course['purchase_code'],
                             'date': row['termination_date'], 'type': row['termination_type'],
                             'before_expiry_net': before_expiry, 'after_expiry_net': proposed['expiry_net'],
                             'before_fee_net': before_fee, 'after_fee_net': proposed['fee_net'],
                             'before_refund_net': before_refund, 'after_refund_net': proposed['refund_net']})
    changed = [row for row in selected if row['difference']]
    before_balance = _sum_exact(row['old_ledger_net'] for row in courses)
    after_balance = _sum_exact(row['standardized_net'] for row in courses)
    return {
        'engine_version': ENGINE_VERSION, 'rule_version': RULE_VERSION,
        'mode': 'dry_run_only_no_database_write', 'cutoff': cutoff,
        'source_meta': data['meta'],
        'source_counts': {key: len(value) for key, value in data.items() if isinstance(value, list)},
        'usage_changed_count': len(changed),
        'usage_affected_purchase_count': len({row['purchase_id'] for row in changed}),
        'usage_net_change': _sum_exact(row['difference'] for row in changed),
        'usage_changes': changed, 'usage_by_month': monthly_usage,
        'course_count': len(courses), 'completed_course_count': sum(row['completed'] for row in courses),
        'old_course_net_balance': before_balance, 'standardized_course_net_balance': after_balance,
        'course_balance_change': _sum_exact((after_balance, before_balance.copy_negate())),
        'courses': courses, 'termination_proposals': term_changes, 'projects': projects,
        'payment_allocations': [row for row in payments if cutoff_day is None or
                                business_date(row['paid_date']) <= cutoff_day],
        'payments_by_month': monthly_payments, 'operations_by_month': operations,
        'operation_lines': operation_lines, 'project_events': project_events,
        'gate': {'backup_export_verified': False, 'restorable_backup_verified': False,
                 'full_restore_test_deferred_by_user': restore_test_deferred,
                 'all_reports_connected': False, 'persisted_net_schema': False,
                 'historical_write_performed': False, 'all_system_consistency_certified': False},
        'limitations': ['體驗、單堂、收款與專案未稅為依規格重建，不冒充原保存未稅。',
                        '含稅金額、付款、時數、日期及ID均未修改。',
                        '期初儲值憑據、含稅退費費用及實際退款日期尚有未決事項。',
                        '本檔不提供資料庫連線、DML、migration或一鍵正式更正功能。'],
    }


def write_markdown(result, parent):
    def amount(value):
        return f'{value:,.0f}'
    changes = ['# 銷課未稅逐筆規格差異（副本試算，未寫回）', '',
               '含稅金額不變。以下只列與新規格不同的未稅值；不是已核准會計更正單。', '',
               '| 入帳日期 | 購買_ID | 堂次 | 原保存未稅 | 規格未稅 | 差異 | 原因 |',
               '|---|---|---:|---:|---:|---:|---|']
    for row in result['usage_changes']:
        changes.append(f"| {row['posting_date']} | {row['purchase_code']} | {row['session_seq']}/{row['total_sessions']} | "
                       f"{amount(row['before_net'])} | {amount(row['after_net'])} | {amount(row['difference'])} | "
                       f"{'最後一堂尾差' if row['reason'] == 'final_tail' else '一般堂固定金額'} |")
    monthly = ['# 每月銷課未稅影響（副本試算）', '',
               '依銷課入帳日分月，不依實際服務日。包含無差異月份；差異為規格值減原保存值。', '',
               '| 月份 | 銷課筆數 | 差異筆數 | 原未稅合計 | 規格未稅合計 | 差異 |',
               '|---|---:|---:|---:|---:|---:|']
    for row in result['usage_by_month']:
        monthly.append(f"| {row['month']} | {row['count']} | {row['changed_count']} | {amount(row['before_net'])} | "
                       f"{amount(row['after_net'])} | {amount(row['difference'])} |")
    review = ['# 歷史資料規格試算摘要 v1.13.17', '', '**未修改正式資料，未提交或部署。**', '',
              f"- 對照銷課：{result['source_counts']['usages']:,} 筆；差異 {result['usage_changed_count']:,} 筆，"
              f"涉及 {result['usage_affected_purchase_count']:,} 筆購課。",
              f"- 銷課未稅全期間合計變動：{amount(result['usage_net_change'])} 元（非含稅收款變動）。",
              f"- 原課程未稅帳務餘額：{amount(result['old_course_net_balance'])} 元；"
              f"規格試算：{amount(result['standardized_course_net_balance'])} 元；"
              f"差異：{amount(result['course_balance_change'])} 元。",
              '- 差異不能只看最後餘額；銷完課程總額可能不變，但每堂與月份分配不同。',
              '- 付款、體驗、單堂及專案未稅由相同規則重建；沒有保存值的欄位不冒充已入帳歷史。', '',
              '## 中止拆分（未稅）', '',
              '| 日期 | 購買_ID | 類型 | 原逾期入帳 | 試算逾期入帳 | 原手續費 | 試算手續費 | 原退款 | 試算退款 |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for row in result['termination_proposals']:
        review.append('| ' + ' | '.join([row['date'], row['purchase_code'], row['type'], *[
            amount(row[key]) for key in ['before_expiry_net', 'after_expiry_net', 'before_fee_net',
                                        'after_fee_net', 'before_refund_net', 'after_refund_net']]]) + ' |')
    review += ['', '## 專案餘額（未稅）', '',
               '| 專案ID | 原餘額算法 | 逐筆規格算法 | 差異 | 期初憑據待查 |', '|---|---:|---:|---:|---|']
    for row in result['projects']:
        review.append(f"| {row['project_id']} | {amount(row['old_net_balance'])} | {amount(row['standardized_net_balance'])} | "
                      f"{amount(row['difference'])} | {'是' if row['opening_provenance_pending'] else '否'} |")
    review += ['', '## 執行門檻與限制', '',
               '- 已依使用者同意暫緩完整還原測試；還原驗證仍為未通過，不新增測試雲端專案。',
               '- 尚未接入全部畫面／下載，也未建立正式未稅保存及更正稽核資料表。',
               '- 正式調整前仍需逐筆核准、最新備份、來源前值核對、分批更正與回復程序。',
               '- 現有規格重建沿用系統既有1.05換算因子，不是對所有歷史交易作稅務認定。',
               '- 本清單不代表已完成歷史更正、銀行對帳或會計入帳。', '',
               f"來源 SHA-256：`{result['source_sha256']}`。"]
    for name, lines in [('銷課逐筆差異.md', changes), ('每月影響.md', monthly), ('試算摘要.md', review)]:
        with (parent / name).open('x', encoding='utf-8') as stream:
            stream.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cutoff', help='可選：yyyy-mm-dd，包含截止日；全課程分配先於日期篩選')
    parser.add_argument('--backup-manifest', type=Path)
    parser.add_argument('--defer-restore-test', action='store_true',
                        help='僅在使用者明確同意時記錄暫緩；不將驗證改為已通過')
    args = parser.parse_args()
    if not args.snapshot.is_file():
        parser.error('財務數值快照不存在。')
    if args.output.exists() or any((args.output.parent / name).exists() for name in
                                 ['銷課逐筆差異.md', '每月影響.md', '試算摘要.md']):
        parser.error('結果已存在，請另指定版本目錄，不覆蓋。')
    raw = args.snapshot.read_bytes()
    result = build_history_proposal(json.loads(raw), args.cutoff,
                                    restore_test_deferred=args.defer_restore_test)
    result['source_sha256'] = sha256(raw).hexdigest()
    if args.backup_manifest:
        manifest = json.loads(args.backup_manifest.read_text(encoding='utf-8'))
        validation = json.loads((args.backup_manifest.parent / 'independent_validation.json').read_text(encoding='utf-8'))
        result['gate']['backup_export_verified'] = (
            manifest['status'] == 'export_verified_restore_pending' and
            validation['all_file_hashes_and_sizes_match'] and validation['all_copy_counts_match'] and
            validation['all_financial_comparisons_match'])
        result['backup_reference'] = {'folder': args.backup_manifest.parent.name,
                                      'export_time': manifest['finished_at_taipei'],
                                      'restore_test_passed': manifest['restore_test_passed']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, default=str)
    write_markdown(result, args.output.parent)
    if sha256(args.snapshot.read_bytes()).hexdigest() != result['source_sha256']:
        raise RuntimeError('試算期間來源檔改變，結果不可使用。')
    print(json.dumps({key: result[key] for key in
                      ['engine_version', 'usage_changed_count', 'usage_affected_purchase_count',
                       'usage_net_change', 'course_balance_change', 'completed_course_count', 'gate']},
                     ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
