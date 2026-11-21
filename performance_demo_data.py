"""合成資料及記憶體工時，供本機展示，絕不連線Supabase。"""
from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace

from coach_performance import month_periods

COACHES = [{'id': 'demo-a', 'username': 'smc001', 'display_name': '虛構教練甲', 'active': True},
           {'id': 'demo-b', 'username': 'smc002', 'display_name': '虛構教練乙', 'active': False},
           {'id': 'demo-c', 'username': 'smc003', 'display_name': '虛構教練丙', 'active': True},
           {'id': 'demo-d', 'username': 'smc004', 'display_name': '虛構停用無資料', 'active': False}]


class PerformanceDemoClient:
    def __init__(self, state, actor='虛構管理員'):
        self.state, self.actor = state, actor
        state.setdefault('demo_hours', {})
        state.setdefault('demo_receipts', {})

    def _hours(self, month):
        return {'month': month, 'coaches': deepcopy(COACHES),
                'hours': [deepcopy(row) for (m, _), row in self.state['demo_hours'].items() if m == month]}

    def rpc(self, name, p):
        if name == 'coach_monthly_work_hours':
            result = self._hours(p['p_month'])
        elif name == 'save_coach_monthly_work_hours':
            receipt_key = (self.actor, p['p_operation_id'])
            old = self.state['demo_receipts'].get(receipt_key)
            if old:
                if old['payload'] != p:
                    raise ValueError('操作識別碼相同但內容不同')
                result = old['result']
            else:
                pending = deepcopy(self.state['demo_hours'])
                for row in p['p_rows']:
                    key = (p['p_month'], row['coach_id'])
                    if pending.get(key, {}).get('revision', 0) != row['revision']:
                        raise ValueError('工時已由其他人修改，請重新載入')
                    pending[key] = {**row, 'month': p['p_month'], 'revision': row['revision'] + 1,
                                    'updated_at': datetime.now().astimezone().isoformat(), 'updated_by_name': self.actor}
                self.state['demo_hours'] = pending
                result = self._hours(p['p_month'])
                self.state['demo_receipts'][receipt_key] = {'payload': deepcopy(p), 'result': deepcopy(result)}
        elif name == 'coach_performance_report':
            start, end = date.fromisoformat(p['p_start']), date.fromisoformat(p['p_end'])
            facts, cohorts = [], []
            for first, last in month_periods(start, end):
                for index, coach in enumerate(COACHES):
                    if coach['id'] == 'demo-d':
                        continue  # 刻意保留在原名單，展示停用且無本期資料時不顯示。
                    day = first.replace(day=min(10, last.day))
                    if first <= day <= last:
                        # 合成數字不是正式業績。
                        n = first.month % 3 + index + 1
                        metrics = {'sales_net': 25000 * n, 'sales_sessions': 20 * n,
                            'first_orders': n, 'renewal_orders': 2, 'usage_net': 10000 * n,
                            'usage_sessions': 20 * n, 'usage_hours': 20 * n,
                            'trial_visits': 6, 'paid_trial_visits': 4, 'trial_hours': 3,
                            'single_hours': 2, 'project_hours': 1, 'oneoff_net': 5000 * n,
                            'completed_courses': 3, 'cancelled_sessions': index + 1,
                            'refund_courses': index, 'refund_net': 2000 * index}
                        facts.extend({'coach_id': coach['id'], 'day': str(day), 'metric': k, 'value': v} for k, v in metrics.items())
                    cohorts.append({'coach_id': coach['id'], 'start_date': str(first), 'end_date': str(last),
                                    'opening_members': 10, 'retained_members': 9 - index})
            if (start, end) not in list(month_periods(start, end)):
                cohorts.extend({'coach_id': c['id'], 'start_date': str(start), 'end_date': str(end),
                                'opening_members': 10, 'retained_members': 8} for c in COACHES if c['id'] != 'demo-d')
            result = {'schema_version': 49, 'start': str(start), 'end': str(end), 'coaches': deepcopy(COACHES),
                      'facts': facts, 'cohorts': cohorts,
                      'hours': [deepcopy(r) for (m, _), r in self.state['demo_hours'].items() if str(start.replace(day=1)) <= m <= str(end.replace(day=1))]}
        else:
            raise ValueError('本機展示不支援此資料操作。')
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=deepcopy(result)))
