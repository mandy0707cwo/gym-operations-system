"""只供離線展示按需建立虛構範例，不載入正式連線。"""
from uuid import uuid4
from copy import deepcopy
from scheduling import dates_in_month,day_payload
from schedule_demo_repository import DemoRepository,DEMO_COACHES
from schedule_allowance import DEDUCT_UNITS


def load_examples(state,month):
    admin={'id':'demo-admin','role':'admin','display_name':'測試管理員'}
    repo=DemoRepository(state,admin)
    if repo.data['days'] or repo.data['months'] or repo.data['leaves']:
        raise ValueError('工作階段已有排班資料，不覆蓋；請另開新的測試頁再載入範例。')
    temporary={'schedule_demo_store':deepcopy(repo.data)}
    repo=DemoRepository(temporary,admin)
    if not repo.allowance_load(month):
        repo.allowance_save(str(uuid4()),{'p_month':month,'p_expected_revision':0,
            'p_payload':{'holidays':[],'deduct_units':dict(DEDUCT_UNITS),'note':'虛構範例額度，非正式假日日曆'}})
    working=[x for x in dates_in_month(month) if x.weekday()!=6]
    for i,person in enumerate(DEMO_COACHES):
        coach=DemoRepository(temporary,person);target=person['id'];rev=0
        def command(action,payload,actor_repo):
            nonlocal rev
            result=actor_repo.command(str(uuid4()),{'p_coach_id':target,'p_month':month,
                'p_expected_revision':rev,'p_action':action,'p_payload':payload})
            rev=result['revision']
        command('apply',{'base_shift':'A'},coach)
        command('save',day_payload(working[1],'B'),coach)
        command('save',day_payload(working[2],'C' if i==0 else 'half_off','10:00' if i==0 else '13:00','16:00' if i==0 else '18:00'),coach)
        command('submit',{},coach);command('approve',{},repo)
        for d,a,b in ((working[0],'09:00','18:00'),(working[3],'13:00','16:00')):
            repo.leave_save(str(uuid4()),{'p_id':str(uuid4()),'p_coach_id':target,'p_month':month,
                'p_expected_revision':0,'p_schedule_revision':rev,'p_action':'save',
                'p_payload':{'work_date':d.isoformat(),'leave_kind':'other','start_time':a,'end_time':b,'reason':'虛構範例，不代表真實請假'}})
    state['schedule_demo_store']=temporary['schedule_demo_store']
    return {'full_absence':working[0].isoformat(),'partial_absence':working[3].isoformat()}
