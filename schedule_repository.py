"""正式排班API與防重送控制；沒有任何service-role回退。"""
from copy import deepcopy
import json
from uuid import uuid4


def object_result(result):
    value=getattr(result,'data',None)
    if isinstance(value,list) and len(value)==1:value=value[0]
    if not isinstance(value,dict):raise ValueError('尚未取得完整操作確認，請查核原操作')
    return value


class ScheduleRepository:
    def __init__(self,client,paged_rows):self.client,self.paged_rows=client,paged_rows
    def load(self,month):
        result=object_result(self.client().rpc('staff_schedule_snapshot',{'p_month':month}).execute())
        if not all(isinstance(result.get(key),list) for key in ('coaches','months','days','preferences')):
            raise ValueError('整月班表回覆不完整，請重新載入')
        return result
    def coach_usernames(self,coach_ids):
        """只讀取當前可選教練的帳號；沿用登入者連線及既有RLS，不以管理金鑰回退。"""
        ids=list(dict.fromkeys(coach_ids))
        if not ids:return {}
        rows=self.paged_rows(lambda:self.client().table('profiles').select('id,username')
            .in_('id',ids).order('id'))
        return {x['id']:x.get('username') or '' for x in rows if x['id'] in ids}
    def logs(self,month,coach):
        return self.paged_rows(lambda:self.client().table('staff_schedule_logs').select('*')
            .eq('month_start',month).eq('coach_id',coach).order('created_at',desc=True).order('id'))
    def command(self,token,args):
        return object_result(self.client().rpc('staff_schedule_command',dict(p_operation_id=token,**args)).execute())
    def status(self,token,cancel=False):
        return object_result(self.client().rpc('staff_schedule_operation',{'p_operation_id':token,'p_cancel':cancel}).execute())
    def allowance_load(self,month):
        result=object_result(self.client().rpc('staff_schedule_allowance_snapshot',{'p_month':month}).execute())
        if 'record' not in result or (result['record'] is not None and not isinstance(result['record'],dict)):
            raise ValueError('排休額度回覆不完整')
        return result['record']
    def allowance_save(self,token,args):
        return object_result(self.client().rpc('staff_schedule_allowance_save',dict(p_operation_id=token,**args)).execute())
    def leave_load(self,month):
        result=object_result(self.client().rpc('staff_schedule_leave_snapshot',{'p_month':month}).execute())
        if not all(isinstance(result.get(k),list) for k in ('records','logs','availability')):
            raise ValueError('請假資料回覆不完整，未顯示為無請假')
        return result
    def leave_save(self,token,args):
        return object_result(self.client().rpc('staff_schedule_leave_save',dict(p_operation_id=token,**args)).execute())


class PendingSchedule:
    """未知結果先查核或保存取消墓碑；不因修改表單就換碼。"""
    def __init__(self,state,repo,actor):
        self.state,self.repo,self.actor=state,repo,actor
        self.key='_schedule_pending_'+str(actor)
    @property
    def data(self):return self.state.get(self.key)
    def send(self,args):
        if self.data and self.data['args']!=args:raise ValueError('尚有未確認排班操作，請先查核或取消')
        if not self.data:self.state[self.key]={'token':str(uuid4()),'args':deepcopy(args)}
        result=self.repo.command(self.data['token'],self.data['args'])
        if not {'revision','state','coach_id','month_start'}<=result.keys():raise ValueError('回覆不完整，請查核原操作')
        del self.state[self.key]
        return result
    def resolve(self,cancel=False):
        if not self.data:return {'state':'not_found'}
        result=self.repo.status(self.data['token'],cancel)
        if result.get('state') in ('completed','cancelled'):del self.state[self.key]
        elif result.get('state')!='not_found':raise ValueError('操作查核回覆不完整')
        return result


def serializable(value):
    return json.dumps(value,ensure_ascii=False,default=str)


def confirm_saved_draft(repo,month,coach,expected_revision,expected_days):
    """日排班已即時寫入；明確重新讀取確認，不製造重複寫入或假成功。"""
    from scheduling import day_payload,dates_in_month
    data=repo.load(month)
    record=next((x for x in data['months'] if x['coach_id']==coach),None)
    if record is None:raise ValueError('目前沒有已儲存的排班，請先填寫日期或套用本月預設班表。')
    if record['state'] not in ('draft','returned'):raise ValueError('班表已送審或核准，不能當作草稿儲存。')
    if record['revision']!=expected_revision:raise ValueError('班表已更新，請重新載入後確認草稿。')
    rows=[x for x in data['days'] if x['coach_id']==coach]
    allowed={x.isoformat() for x in dates_in_month(month)}
    def normalized(items):
        result={}
        for x in items:
            p=day_payload(x['work_date'],x['shift_code'],x.get('start_time'),x.get('end_time'),x.get('note'))
            if p['work_date'] not in allowed or p['work_date'] in result:
                raise ValueError('草稿日期有重複或不屬於本月，請重新查核。')
            result[p['work_date']]=p
        return result
    saved=normalized(rows)
    if saved!=normalized(expected_days):raise ValueError('草稿內容與畫面不同，請重新載入後確認。')
    if not saved:raise ValueError('目前沒有已儲存的排班，請先填寫日期或套用本月預設班表。')
    return {'saved_days':len(saved),'total_days':len(allowed),'state':record['state']}
