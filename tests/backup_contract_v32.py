"""只正規化v32已明列的備份來源差異，其他App內容必須與舊基準完全一致。"""
def normalize_backup_source(source):
    replacements={
        '        "staff_schedule_special_months":"特殊假別月份",\n':'',
        '        "staff_schedule_special_days":"統一特殊假別",\n':'',
        'table_name in ("staff_schedule_allowances","staff_schedule_special_months") else "work_date" if table_name=="staff_schedule_special_days"':
        'table_name=="staff_schedule_allowances"',
        '私有schema紀錄（操作收據及特殊假別稽核）':'私有操作收據',
    }
    for before,after in replacements.items():
        if source.count(before)!=1:raise AssertionError('備份差異不符已核准範圍：'+before)
        source=source.replace(before,after,1)
    return source
