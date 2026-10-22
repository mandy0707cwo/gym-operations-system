"""請假異動沿用原操作識別碼、查核及取消墓碑。"""
from copy import deepcopy
from uuid import uuid4


class PendingLeave:
    def __init__(self,state,repo,actor):
        self.state,self.repo=state,repo
        self.key='_schedule_leave_pending_'+actor
    @property
    def data(self):return self.state.get(self.key)
    def send(self,args):
        if self.data and self.data['args']!=args:raise ValueError('請假操作尚未確認，請先查核或取消')
        if not self.data:self.state[self.key]={'token':str(uuid4()),'args':deepcopy(args)}
        result=self.repo.leave_save(self.data['token'],self.data['args'])
        if not isinstance(result,dict) or not {'id','revision','state','coach_id','month_start'}<=result.keys() or result['state'] not in ('active','void'):
            raise ValueError('請假回覆不完整，請查核原操作')
        if (result['id'],result['coach_id'],result['month_start'],result['revision'],result['state'])!=(
            args['p_id'],args['p_coach_id'],args['p_month'],args['p_expected_revision']+1,'void' if args['p_action']=='void' else 'active'):
            raise ValueError('請假回覆與原操作不一致，請查核原操作')
        del self.state[self.key]
        return result
    def resolve(self,cancel=False):
        if not self.data:return {'state':'not_found'}
        result=self.repo.status(self.data['token'],cancel)
        if result.get('state') in ('completed','cancelled'):del self.state[self.key]
        elif result.get('state')!='not_found':raise ValueError('請假查核回覆不完整')
        return result
