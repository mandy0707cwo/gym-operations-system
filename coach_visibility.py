"""教練績效共用顯示規則；不刪來源、不變更指標或分母。"""


def visible_coaches(engine):
    """保留啟用者，以及本期仍有績效計算依據的停用者。"""
    # 按「有紀錄」判斷，不以金額>0判斷：免費體驗、沖回及抵銷也須保留。
    evidence = {coach for coach, _, _, _ in engine.facts}
    for coach in engine.coaches:
        key = (coach['id'], str(engine.start), str(engine.end))
        if engine.cohorts.get(key, (0, 0))[0] > 0:
            evidence.add(coach['id'])  # 本期會員維持率仍有分母。
    evidence.update(coach for (coach, month), hours in engine.hours.items()
                    if hours > 0 and str(engine.start.replace(day=1)) <= month <= str(engine.end.replace(day=1)))
    result = []
    for coach in engine.coaches:
        active = coach.get('active', True)  # 相容舊版虛構／離線來源；正式RPC均有布林欄位。
        if type(active) is not bool:
            raise ValueError('教練啟用狀態無效，請重新查詢。')
        if active or coach['id'] in evidence:
            result.append(coach)
    return result
