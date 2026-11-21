"""正常登入身分呼叫受控RPC；不使用service role，不向主管開放原始中止表。"""
def require_management(me):
    if me.get('role') not in ('manager', 'admin'):
        raise PermissionError('此功能僅供主管與系統管理員。')


def fetch_report(connection, me, start, end):
    require_management(me)
    return connection.rpc('coach_performance_report', {'p_start': str(start), 'p_end': str(end)}).execute().data


def fetch_hours(connection, me, month):
    require_management(me)
    result = connection.rpc('coach_monthly_work_hours', {'p_month': str(month)}).execute().data
    if not isinstance(result, dict) or result.get('month') != str(month):
        raise ValueError('每月工時回傳期間不符。')
    return result


def save_hours(connection, me, operation_id, month, rows):
    require_management(me)
    result = connection.rpc('save_coach_monthly_work_hours', {
        'p_operation_id': operation_id, 'p_month': str(month), 'p_rows': rows}).execute().data
    if not isinstance(result, dict) or result.get('month') != str(month):
        raise ValueError('儲存結果尚未確認，請使用相同操作重試。')
    return result
