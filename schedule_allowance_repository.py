"""額度確認操作：保留原操作碼與取消墓碑，不因重試產生第二筆稽核。"""
from copy import deepcopy
from uuid import uuid4


class PendingAllowance:
    def __init__(self,state,repo,actor):
        self.state,self.repo=state,repo
        self.key='_schedule_allowance_pending_'+actor
    @property
    def data(self):return self.state.get(self.key)
    def send(self,args):
        if self.data and self.data['args']!=args:raise ValueError('額度操作尚未確認，請先查核或取消')
        if not self.data:self.state[self.key]={'token':str(uuid4()),'args':deepcopy(args)}
        result=self.repo.allowance_save(self.data['token'],self.data['args'])
        if not isinstance(result,dict) or not {'month_start','revision','state','total_units'}<=result.keys():
            raise ValueError('額度回覆不完整，請查核原操作')
        if result['state']!='confirmed':raise ValueError('額度狀態未確認')
        del self.state[self.key]
        return result
    def resolve(self,cancel=False):
        if not self.data:return {'state':'not_found'}
        result=self.repo.status(self.data['token'],cancel)
        if result.get('state') in ('completed','cancelled'):del self.state[self.key]
        elif result.get('state')!='not_found':raise ValueError('額度查核回覆不完整')
        return result
