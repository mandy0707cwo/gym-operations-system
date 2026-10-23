"""教練本頁預排；按草稿／送出前不寫入後端，不混用不同月份或版本。"""
from copy import deepcopy
from scheduling import day_payload,fill_empty,first_day
from schedule_allowance import allowance_totals
from schedule_special import special_projection


class CoachDraft:
    def __init__(self,state,actor,month,revision):
        self.state=state;self.actor=actor;self.month=month
        self.key=f'_coach_draft_{actor}_{month}'
        self.data=state.setdefault(self.key,{'revision':revision,'days':{},'base':None,'epoch':0})
        if not self.dirty and self.data['revision']!=revision:
            self.data['revision']=revision;self.data['epoch']+=1
        self.conflict=self.data['revision']!=revision
    @property
    def dirty(self):return bool(self.data['days'] or self.data['base'])
    def clear(self):self.state.pop(self.key,None)
    def merged(self,rows):
        values={str(x['work_date'])[:10]:deepcopy(x) for x in rows if x['coach_id']==self.actor}
        values.update({k:dict(v,coach_id=self.actor,month_start=self.month) for k,v in self.data['days'].items()})
        return list(values.values())
    def stage(self,action,payload,rows):
        if self.conflict:raise ValueError('班表已被更新，請先放棄本頁預排並重新載入')
        if action=='save':
            value=day_payload(payload['work_date'],payload['shift_code'],payload.get('start_time'),payload.get('end_time'),payload.get('note'))
            if first_day(value['work_date']).isoformat()!=self.month:raise ValueError('日期不在目前月份')
            old=next((x for x in rows if x['coach_id']==self.actor and x['work_date']==value['work_date']),{})
            if value['shift_code'] in ('public_off','weekend') or old.get('shift_code')=='public_off':raise ValueError('此班別須由主管或管理者設定')
            self.data['days'][value['work_date']]=value
        elif action=='apply':
            values=fill_empty(self.month,payload.get('base_shift'),self.merged(rows))
            self.data['base']=payload['base_shift']
            for value in values:self.data['days'][value['work_date']]=value
        else:raise ValueError('不支援的預排動作')
        self.data['epoch']+=1
    def totals(self,record,rows,specials):
        projected=special_projection({'days':self.merged(rows)},specials)['days']
        return allowance_totals(record,projected,self.month,self.actor)
    def payload(self):
        result={'days':[deepcopy(self.data['days'][d]) for d in sorted(self.data['days'])]}
        if self.data['base']:result['base_shift']=self.data['base']
        return result


def validate_quota(record,rows,month,actor,specials):
    totals=allowance_totals(record,special_projection({'days':rows},specials)['days'],month,actor)
    if totals is None:raise ValueError('本月排休額度尚未核定，教練不能排班或儲存')
    if totals['remaining_units']<0:raise ValueError('超出本月排休額度，不能儲存草稿或送出')
    return totals
