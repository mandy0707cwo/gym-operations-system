"""明確隔離的虛構試操作來源，僅供UI試用；不是正式權限或持久資料庫。"""
from copy import deepcopy
from datetime import datetime,timezone
from uuid import uuid4
from scheduling import ROLES,REVIEWERS,STATES,day_payload,fill_empty,first_day,dates_in_month
from schedule_allowance import normalize_allowance
from schedule_leave import leave_payload,validate_leave,guard_schedule_leave,availability
from schedule_special import normalize_special
from schedule_special import active_specials
from schedule_draft import validate_quota

DEMO_COACHES=[{'id':'demo-a','username':'demo001','display_name':'測試教練甲','active':True,'role':'coach'},
              {'id':'demo-b','username':'demo002','display_name':'測試教練乙','active':True,'role':'coach'}]


class DemoRepository:
    def __init__(self,state,me):
        self.state,self.me=state,me
        state.setdefault('schedule_demo_store',{'months':{},'days':{},'preferences':{},'logs':[],'receipts':{}})
        state['schedule_demo_store'].setdefault('allowances',{})
        state['schedule_demo_store'].setdefault('allowance_logs',[])
        state['schedule_demo_store'].setdefault('leaves',{})
        state['schedule_demo_store'].setdefault('leave_logs',[])
        state['schedule_demo_store'].setdefault('specials',{})
        state['schedule_demo_store'].setdefault('special_logs',[])
    @property
    def data(self):return self.state['schedule_demo_store']
    def check(self):
        if self.me['role'] not in ROLES:raise ValueError('帳號無排班權限')
    def load(self,month):
        self.check()
        reviewer=self.me['role'] in REVIEWERS
        months=[deepcopy(v) for (c,m),v in self.data['months'].items()
                if m==month and (reviewer or c==self.me['id'] or v['state']=='approved')]
        visible={v['coach_id'] for v in months}
        return {'coaches':deepcopy(DEMO_COACHES),'months':months,
            'days':[deepcopy(v) for (c,d),v in self.data['days'].items() if d[:7]==month[:7] and c in visible],
            'preferences':[{'coach_id':c,'base_shift':s} for c,s in self.data['preferences'].items()
                           if reviewer or c==self.me['id']]}
    def logs(self,month,coach):
        self.check()
        if self.me['role']=='coach' and self.me['id']!=coach:raise ValueError('無權查看他人異動紀錄')
        return [deepcopy(x) for x in reversed(self.data['logs']) if x['month_start']==month and x['coach_id']==coach]
    def coach_usernames(self,coach_ids):
        self.check()
        return {x['id']:x.get('username') or '' for x in DEMO_COACHES if x['id'] in coach_ids}
    def status(self,token,cancel=False):
        self.check();key=(self.me['id'],token)
        if key in self.data['receipts']:return deepcopy(self.data['receipts'][key])
        if cancel:self.data['receipts'][key]={'state':'cancelled'};return {'state':'cancelled'}
        return {'state':'not_found'}
    def allowance_load(self,month):
        self.check()
        return deepcopy(self.data['allowances'].get(month))
    def special_load(self,month):
        self.check()
        return deepcopy(self.data['specials'].get(month,{'revision':0,'days':[]}))
    def special_save(self,token,args):
        self.check()
        if self.me['role'] not in REVIEWERS:raise ValueError('僅主管及管理者可設定特殊假別')
        key=(self.me['id'],token);marker=dict(args,type='special');receipt=self.data['receipts'].get(key)
        if receipt:
            if receipt['state']=='cancelled':raise ValueError('操作已取消')
            if receipt['args']!=marker:raise ValueError('操作識別碼內容不同')
            return deepcopy(receipt['result'])
        month=args['p_month'];action=args['p_action'];payload=args['p_payload']
        if action not in ('save','void'):raise ValueError('特殊假別動作無效')
        normalized=normalize_special(month,payload)
        store=deepcopy(self.data);record=deepcopy(store['specials'].get(month,{'revision':0,'days':[]}))
        if record['revision']!=args['p_expected_revision']:raise ValueError('特殊假別已更新，請重新載入')
        before=deepcopy(record);by_date={x['work_date']:x for x in record['days']}
        selected=[d.isoformat() for d in dates_in_month(month) if normalized['date_from']<=d.isoformat()<=normalized['date_to']]
        if action=='void' and not any(by_date.get(d,{}).get('state')=='active' for d in selected):raise ValueError('所選日期沒有有效特殊假別')
        for d in selected:
            if action=='save':by_date[d]=dict(work_date=d,month_start=month,state='active',**{k:normalized[k] for k in ('kind','label','start_time','end_time','deduct_units')})
            elif d in by_date:by_date[d]['state']='void'
        record.update(revision=record['revision']+1,days=sorted(by_date.values(),key=lambda x:x['work_date']))
        result={'month_start':month,'revision':record['revision'],'state':'confirmed','action':action}
        store['specials'][month]=record
        store['special_logs'].append({'actor_id':self.me['id'],'reason':normalized['reason'],'before_value':before,'after_value':deepcopy(record)})
        store['receipts'][key]={'state':'completed','args':marker,'result':deepcopy(result)}
        self.state['schedule_demo_store']=store
        return result
    def allowance_save(self,token,args):
        self.check()
        if self.me['role'] not in REVIEWERS:raise ValueError('僅主管或系統管理員可確認排休額度')
        key=(self.me['id'],token);receipt=self.data['receipts'].get(key)
        marker=dict(args,type='allowance')
        if receipt:
            if receipt['state']=='cancelled':raise ValueError('操作已取消')
            if receipt['args']!=marker:raise ValueError('操作識別碼內容不同')
            return deepcopy(receipt['result'])
        normalized=normalize_allowance(args['p_month'],args['p_payload'])
        originals={x['original_date'] for x in normalized['holidays']}
        if any(x['original_date'] in originals for month,entry in self.data['allowances'].items()
               if month!=args['p_month'] for x in entry['holidays']):
            raise ValueError('同一原假日已計入其他月份，請先核對原月份')
        store=deepcopy(self.data);old=store['allowances'].get(args['p_month'])
        revision=old['revision'] if old else 0
        if revision!=args['p_expected_revision']:raise ValueError('額度已更新，請重新載入')
        result=dict(normalized,revision=revision+1,confirmed_by=self.me['id'],confirmed_name=self.me['display_name'],
                    updated_at=datetime.now(timezone.utc).isoformat(),state='confirmed')
        store['allowances'][args['p_month']]=deepcopy(result)
        store['allowance_logs'].append({'month_start':args['p_month'],'actor_id':self.me['id'],
            'before_value':deepcopy(old),'after_value':deepcopy(result)})
        store['receipts'][key]={'state':'completed','args':deepcopy(marker),'result':deepcopy(result)}
        self.state['schedule_demo_store']=store
        return result
    def leave_load(self,month):
        self.check();reviewer=self.me['role'] in REVIEWERS
        rows=[deepcopy(x) for x in self.data['leaves'].values() if x['month_start']==month]
        return {'records':[x for x in rows if reviewer or x['coach_id']==self.me['id']],
            'logs':[deepcopy(x) for x in self.data['leave_logs'] if x['month_start']==month and (reviewer or x['coach_id']==self.me['id'])],
            'availability':availability(rows,self.load(month))}
    def leave_save(self,token,args):
        self.check()
        if self.me['role'] not in REVIEWERS:raise ValueError('僅主管或系統管理員可登錄請假')
        marker=dict(args,type='leave');key=(self.me['id'],token);receipt=self.data['receipts'].get(key)
        if receipt:
            if receipt['state']=='cancelled':raise ValueError('操作已取消')
            if receipt['args']!=marker:raise ValueError('操作識別碼內容不同')
            return deepcopy(receipt['result'])
        coach,month,id=args['p_coach_id'],args['p_month'],args['p_id']
        if coach not in {x['id'] for x in DEMO_COACHES}:raise ValueError('對象不是有效教練')
        old=self.data['leaves'].get(id);revision=old['revision'] if old else 0
        if revision!=args['p_expected_revision']:raise ValueError('請假已更新，請重新載入')
        if old and (old['coach_id']!=coach or old['month_start']!=month or old['state']!='active'):
            raise ValueError('請假紀錄無效或已作廢')
        action=args['p_action'];reason=args['p_payload'].get('reason')
        if not isinstance(reason,str) or not reason.strip() or len(reason.strip())>1000:raise ValueError('請填寫1000字內的登錄／修改原因')
        if action=='save':
            value=leave_payload(month,args['p_payload'])
            validate_leave(self.load(month),list(self.data['leaves'].values()),coach,month,value,id)
            current=self.data['months'][(coach,month)]
            if current['revision']!=args['p_schedule_revision']:raise ValueError('班表已更新，請重新載入')
        elif action=='void' and old:value={k:old[k] for k in ('work_date','leave_kind','start_time','end_time','minutes')};value['reason']=reason.strip()
        else:raise ValueError('不支援的請假操作')
        store=deepcopy(self.data);now=datetime.now(timezone.utc).isoformat()
        result=dict(value,id=id,coach_id=coach,month_start=month,state='active' if action=='save' else 'void',
                    revision=revision+1,actor_id=self.me['id'],actor_name=self.me['display_name'],updated_at=now)
        store['leaves'][id]=deepcopy(result)
        store['leave_logs'].append({'id':str(uuid4()),'leave_id':id,'coach_id':coach,'month_start':month,
            'actor_id':self.me['id'],'actor_name':self.me['display_name'],'action':action,'reason':reason.strip(),
            'before_value':deepcopy(old),'after_value':deepcopy(result),'created_at':now})
        store['receipts'][key]={'state':'completed','args':deepcopy(marker),'result':deepcopy(result)}
        self.state['schedule_demo_store']=store
        return result
    def command(self,token,args):
        self.check();key=(self.me['id'],token)
        if key in self.data['receipts']:
            receipt=self.data['receipts'][key]
            if receipt['state']=='cancelled':raise ValueError('操作已取消')
            if receipt['args']!=args:raise ValueError('操作識別碼內容不同')
            return deepcopy(receipt['result'])
        role=self.me['role'];coach=args['p_coach_id'];month=args['p_month'];action=args['p_action'];payload=args.get('p_payload',{})
        if first_day(month).isoformat()!=month:raise ValueError('月份必須為月初')
        if coach not in {c['id'] for c in DEMO_COACHES}:raise ValueError('排班對象不是有效教練')
        if role=='coach' and self.me['id']!=coach:raise ValueError('教練只能修改自己的班表')
        store=deepcopy(self.data)
        record=store['months'].setdefault((coach,month),{'coach_id':coach,'month_start':month,
            'coach_name':next(c['display_name'] for c in DEMO_COACHES if c['id']==coach),'state':'draft','revision':0})
        if record['revision']!=args['p_expected_revision']:raise ValueError('班表已更新，請重新載入')
        before=deepcopy(record);before_data=None;after_data=None;reason=str(payload.get('reason') or payload.get('note') or '').strip()
        if len(reason)>1000:raise ValueError('說明不可超過1000字')
        if role=='coach' and record.get('coach_locked'):raise ValueError('本月已確認儲存，只有主管及管理者可修改')
        if action in ('draft','draft_submit'):
            if role!='coach' or record.get('coach_locked') or record['state'] not in ('draft','returned'):
                raise ValueError('僅教練可儲存自己的未鎖定草稿')
            values=payload.get('days')
            if not isinstance(values,list) or len(values)>31:raise ValueError('預排日期須為最多31筆清單')
            if any(not isinstance(x,dict) for x in values):raise ValueError('預排日期內容須為物件')
            if len({x.get('work_date') for x in values})!=len(values):raise ValueError('預排日期重複')
            before_data=[];after_data=[]
            for x in values:
                value=day_payload(x['work_date'],x['shift_code'],x.get('start_time'),x.get('end_time'),x.get('note'))
                if first_day(value['work_date']).isoformat()!=month:raise ValueError('日期不在目前月份')
                old=store['days'].get((coach,value['work_date']))
                if value['shift_code'] in ('public_off','weekend') or old and old['shift_code']=='public_off':raise ValueError('此班別須由主管或管理者設定')
                guard_schedule_leave(dict(value,coach_id=coach),list(store['leaves'].values()))
                before_data.append(deepcopy(old));after_data.append(value)
                store['days'][(coach,value['work_date'])]=dict(value,coach_id=coach,month_start=month)
            if 'base_shift' in payload:
                if payload['base_shift'] not in ('A','B'):raise ValueError('預設班別無效')
                store['preferences'][coach]=payload['base_shift']
            if action=='draft_submit':
                if len([1 for c,d in store['days'] if c==coach and d[:7]==month[:7]])!=len(dates_in_month(month)):
                    raise ValueError('整月尚有未填日期')
                record.update(state='submitted',coach_locked=True,review_reason='',
                    finalized_at=datetime.now(timezone.utc).isoformat(),finalized_by=self.me['id'])
        elif action in ('save','fill','default','apply'):
            if role=='coach' and record['state'] not in ('draft','returned'):raise ValueError('送審或核准後不可修改')
            if action=='default':
                base=payload.get('base_shift')
                if base not in ('A','B'):raise ValueError('請選擇A班或B班')
                before_data=store['preferences'].get(coach);store['preferences'][coach]=base;after_data={'base_shift':base}
            elif action in ('fill','apply'):
                previous=store['preferences'].get(coach)
                if action=='apply':
                    base=payload.get('base_shift')
                    if base not in ('A','B'):raise ValueError('請選擇A班或B班')
                    before_data={'base_shift':previous}
                    store['preferences'][coach]=base
                else:
                    base=previous
                    if payload.get('base_shift')!=base:raise ValueError('預設班別已變更，請重新載入')
                existing=[v for (c,d),v in store['days'].items() if c==coach and d[:7]==month[:7]]
                after_data=fill_empty(month,base,existing)
                for v in after_data:store['days'][(coach,v['work_date'])]=dict(v,coach_id=coach,month_start=month)
                if action=='apply':after_data={'base_shift':base,'added_days':after_data}
            else:
                old=store['days'].get((coach,str(payload.get('work_date'))),{})
                if role=='coach' and (payload.get('shift_code')=='public_off' or old.get('shift_code')=='public_off'):
                    raise ValueError('公休須由主管及管理者設定')
                v=day_payload(payload['work_date'],payload['shift_code'],payload.get('start_time'),payload.get('end_time'),payload.get('note'))
                if first_day(v['work_date']).isoformat()!=month:raise ValueError('日期不在目前月份')
                before_data=store['days'].get((coach,v['work_date']));after_data=v
                guard_schedule_leave(dict(v,coach_id=coach),list(store['leaves'].values()))
                store['days'][(coach,v['work_date'])]=dict(v,coach_id=coach,month_start=month)
        elif action=='submit':
            if role!='coach' or record['state'] not in ('draft','returned'):raise ValueError('僅本人可送審草稿或退回班表')
            if len([1 for c,d in store['days'] if c==coach and d[:7]==month[:7]])!=len(dates_in_month(month)):
                raise ValueError('整月尚有未填日期')
            record.update(state='submitted',review_reason='',coach_locked=True,
                finalized_at=datetime.now(timezone.utc).isoformat(),finalized_by=self.me['id'])
        elif action=='manager_confirm':
            if role not in REVIEWERS:raise ValueError('僅主管及管理者可代填完成並核准')
            if len([1 for c,d in store['days'] if c==coach and d[:7]==month[:7]])!=len(dates_in_month(month)):
                raise ValueError('整月尚有未填日期')
            if not record.get('coach_locked'):
                record.update(finalized_at=datetime.now(timezone.utc).isoformat(),finalized_by=self.me['id'])
            record.update(state='approved',coach_locked=True,review_reason=reason)
        elif action=='withdraw':
            if role!='coach' or record['state']!='submitted':raise ValueError('只能撤回自己的待審班表')
            record['state']='draft'
        elif action in ('approve','return'):
            if role not in REVIEWERS:raise ValueError('僅主管或系統管理員可審核')
            if action=='approve' and record['state']!='submitted':raise ValueError('僅待審班表可核准')
            if action=='return' and (record['state'] not in ('submitted','approved') or not reason):raise ValueError('退回須填寫原因')
            record.update(state='approved' if action=='approve' else 'returned',review_reason=reason)
        else:raise ValueError('不支援的排班操作')
        if role=='coach' and action in ('save','fill','default','apply','draft','draft_submit','submit'):
            rows=[v for (c,d),v in store['days'].items() if c==coach and d[:7]==month[:7]]
            validate_quota(store['allowances'].get(month),rows,month,coach,
                active_specials(store['specials'].get(month,{'days':[]}),month))
        record['revision']+=1
        result={k:record[k] for k in ('coach_id','month_start','state','revision')};result['action']=action
        store['logs'].append({'id':str(uuid4()),'coach_id':coach,'month_start':month,'action':action,
            'actor_id':self.me['id'],'actor_name':self.me['display_name'],'reason':reason,
            'before_value':{'month':before,'data':deepcopy(before_data)},'after_value':{'month':deepcopy(record),'data':deepcopy(after_data)},
            'created_at':datetime.now(timezone.utc).isoformat()})
        store['receipts'][key]={'state':'completed','result':deepcopy(result),'args':deepcopy(args)}
        self.state['schedule_demo_store']=store
        return result
