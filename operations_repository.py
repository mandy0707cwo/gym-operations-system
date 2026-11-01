"""營運管理只讀來源；以登入者連線沿用RLS，不使用管理金鑰。"""
from operations_metrics import Period, day


def paged(builder, page_size=1000):
    records = []
    offset = 0
    while True:
        batch = builder().range(offset, offset + page_size - 1).execute().data or []
        records.extend(batch)
        if len(batch) < page_size:
            return records
        offset += page_size


def load_sources(connection, owner, start, end):
    if owner.get('role') not in ('manager', 'admin'):
        raise PermissionError('營運管理僅限主管與系統管理員。')
    Period(start, end)
    # 購課與銷課必須含截止日前全部歷史，不能只讀本月最後一堂。
    purchases = paged(lambda: connection.table('purchases').select(
        'id,purchase_date,purchase_kind,total_sessions,total_amount,total_net_amount,calculation_rule_version'
    ).lte('purchase_date', str(end)).order('id'))
    usages = paged(lambda: connection.table('session_usages').select(
        'id,purchase_id,usage_date,created_at,deducted_net_amount'
    ).lte('usage_date', str(end)).order('id'))
    trials = paged(lambda: connection.table('trial_items').select(
        'id,entry_date,amount'
    ).gte('entry_date', str(start)).lte('entry_date', str(end)).order('id'))
    completed = connection.rpc('operations_completed_counts', {'p_start': str(start), 'p_end': str(end)}).execute().data
    if not isinstance(completed, list):
        raise ValueError('課程完成統計未完整回傳，請重新查詢。')
    for row in completed:
        if set(row) != {'completed_date', 'completed_courses'} or not (start <= day(row['completed_date']) <= end):
            raise ValueError('課程完成統計格式或日期範圍不符。')
    return {'purchases': purchases, 'session_usages': usages,
            'trial_items': trials, 'completed_counts': completed}
