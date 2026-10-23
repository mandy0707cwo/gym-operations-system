"""管理者特殊假別與完成簡表；不列異動紀錄，不使用正式寫入試操作。"""
from copy import deepcopy
from datetime import date,time
from uuid import uuid4
import pandas as pd
import streamlit as st
from scheduling import REVIEWERS,dates_in_month
from schedule_special import SPECIAL_KINDS,normalize_special,progress_rows
from schedule_allowance import allowance_totals


class PendingSpecial:
    def __init__(self,state,repo,actor):
        self.state,self.repo=state,repo;self.key='_schedule_special_pending_'+actor
    @property
    def data(self):return self.state.get(self.key)
    def send(self,args):
        if self.data and self.data['args']!=args:raise ValueError('特殊假別操作尚未確認，請先查核或取消')
        if not self.data:self.state[self.key]={'token':str(uuid4()),'args':deepcopy(args)}
        result=self.repo.special_save(self.data['token'],self.data['args'])
        if not isinstance(result,dict) or not {'month_start','revision','state'}<=result.keys() or result['state']!='confirmed':
            raise ValueError('特殊假別回覆不完整，請查核原操作')
        del self.state[self.key];return result
    def resolve(self,cancel=False):
        if not self.data:return {'state':'not_found'}
        result=self.repo.status(self.data['token'],cancel)
        if result.get('state') in ('completed','cancelled'):del self.state[self.key]
        elif result.get('state')!='not_found':raise ValueError('特殊假別查核回覆不完整')
        return result


def render_progress(me,repo,data,month):
    if me.get('role') not in REVIEWERS:st.warning('僅主管及管理者可查看排休進度。');return
    try:
        ids=[x['id'] for x in data['coaches'] if x.get('active',True)]
        result=progress_rows(me,data,month,repo.coach_usernames(ids))
        allowance=repo.allowance_load(month)
        for row,coach in zip(result,[x for x in data['coaches'] if x.get('active',True)]):
            totals=allowance_totals(allowance,data['days'],month,coach['id']) if allowance else None
            row.update({'可排休（天）':totals['total_units']/2 if totals else None,
                '已排休（天）':totals['used_units']/2 if totals else None,
                '剩餘額度（天）':totals['remaining_units']/2 if totals else None})
    except Exception as exc:st.error(f'排休進度讀取失敗，未顯示假完成：{exc}');return
    done=sum(x['排休進度']=='已完成' for x in result)
    with st.container(horizontal=True):
        st.metric('教練人數',len(result));st.metric('已完成',done);st.metric('未完成',len(result)-done)
    for row in result:
        if row['確認時間'] and not row['確認時間'].startswith('歷史'):
            row['確認時間']=pd.to_datetime(row['確認時間'],utc=True).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M')
    st.dataframe(pd.DataFrame(result),hide_index=True,width='stretch')
    st.caption('完成＝已填完整月並確認儲存；填滿但未確認仍是未完成。確認後只有主管及管理者能修改。確認時間為台灣時間，核准狀態另列。')


def special_settings(me,repo,month,snapshot):
    if me.get('role') not in REVIEWERS:st.warning('僅主管及管理者可設定特殊假別。');return
    def stay():st.session_state['_schedule_force_tab_'+me['id']]='特殊假別設定'
    pending=PendingSpecial(st.session_state,repo,me['id'])
    if pending.data:
        st.warning('特殊假別操作尚未確認，請先查核、原碼重試或取消。')
        try:
            with st.container(horizontal=True):
                if st.button('查核特殊假別操作',on_click=stay):pending.resolve();st.rerun()
                if st.button('原碼重試特殊假別操作',on_click=stay):pending.send(pending.data['args']);st.rerun()
                if st.button('取消未確認特殊假別操作',on_click=stay):pending.resolve(cancel=True);st.rerun()
        except Exception as exc:st.error(str(exc))
        if pending.data:return
    revision=snapshot['revision'];active=[x for x in snapshot['days'] if x['state']=='active']
    if active:
        st.dataframe(pd.DataFrame([{'日期':date.fromisoformat(x['work_date']),'假別':x['label'],
            '時段':f'{x["start_time"][:5]}–{x["end_time"][:5]}' if x.get('start_time') else '整日',
            '該日扣額度（天）':x['deduct_units']/2} for x in active]),hide_index=True,width='stretch',
            column_config={'日期':st.column_config.DateColumn(format='YYYY-MM-DD')})
    else:st.info('本月尚無統一特殊假別。')
    st.caption('設定適用全體教練，包括已確認及已核准班表；原班別保留，作廢後恢復原班表顯示。每個日期一筆，重設同日會取代原特殊假別。')
    prefix=f'special_{me["id"]}_{month}_{revision}'
    kind=st.selectbox('特殊假別',list(SPECIAL_KINDS),format_func=SPECIAL_KINDS.get,index=None,key=prefix+'_kind',on_change=stay)
    st.caption('特殊假別為整日休；本版不設定部分時段。')
    available=dates_in_month(month)
    with st.form(prefix+'_save'):
        pair=st.columns(2)
        start=pair[0].date_input('開始日期',value=available[0],min_value=available[0],max_value=available[-1])
        end=pair[1].date_input('結束日期',value=available[0],min_value=available[0],max_value=available[-1])
        label=st.text_input('假別顯示名稱',value=SPECIAL_KINDS.get(kind,''),max_chars=100)
        a=b=None
        units=st.selectbox('該日排休扣額度（每日期合計）',[0,1,2],index=None,
            format_func=lambda x:{0:'不扣額度',1:'扣0.5天',2:'扣1天'}[x])
        st.caption('此設定取代該日期原排休扣額度，不與整日休／半日休／公休重複相加；不增加每月核定可排休天數。')
        reason=st.text_input('特殊假別設定／修改原因',max_chars=1000)
        confirmed=st.checkbox('確認套用全體教練及已核准班表，並已核對該日扣額度')
        if st.form_submit_button('儲存特殊假別設定',type='primary',on_click=stay):
            try:
                if not confirmed:raise ValueError('請勾選套用確認')
                payload=normalize_special(month,{'date_from':start,'date_to':end,'kind':kind,'label':label,
                    'start_time':a.isoformat(timespec='minutes') if a else None,'end_time':b.isoformat(timespec='minutes') if b else None,
                    'deduct_units':units,'reason':reason})
                pending.send({'p_month':month,'p_expected_revision':revision,'p_action':'save','p_payload':payload})
                st.session_state['_special_flash']=True;stay();st.rerun()
            except Exception as exc:st.error(f'特殊假別未確認：{exc}')
    if active:
        with st.expander('作廢特殊假別（不刪除紀錄）'):
            with st.form(prefix+'_void'):
                selected=st.selectbox('作廢日期',[x['work_date'] for x in active],index=None)
                reason=st.text_input('作廢原因',max_chars=1000)
                ack=st.checkbox('確認恢復此日原班表與原扣額度')
                if st.form_submit_button('確認作廢特殊假別',on_click=stay):
                    try:
                        if not ack or selected not in {x['work_date'] for x in active}:raise ValueError('請選日期並確認')
                        payload=normalize_special(month,{'date_from':selected,'date_to':selected,'kind':'other','label':'作廢',
                            'deduct_units':0,'reason':reason})
                        pending.send({'p_month':month,'p_expected_revision':revision,'p_action':'void','p_payload':payload})
                        st.session_state['_special_flash']=True;stay();st.rerun()
                    except Exception as exc:st.error(f'作廢未確認：{exc}')
    if st.session_state.pop('_special_flash',False):st.success('特殊假別已確認套用。')
