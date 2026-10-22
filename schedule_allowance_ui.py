"""額度確認與精簡提示；沒有填入任何推測的國定假日。"""
from datetime import date
import pandas as pd
import streamlit as st
from scheduling import dates_in_month
from schedule_allowance import DEDUCT_UNITS,normalize_allowance,allowance_totals,days_text
from schedule_allowance_repository import PendingAllowance
from schedule_leave import allowance_overview


def allowance_banner(me,repo,month,coach,days):
    try:
        record=repo.allowance_load(month)
        totals=allowance_totals(record,days,month,coach)
    except Exception as exc:
        st.error(f'排休額度讀取失敗，未以0天代替：{exc}')
        return
    if totals is None:
        st.caption('本月排休額度尚未設定，請系統管理員核對並確認。')
        return
    st.markdown(f'本月可排休 **{days_text(totals["total_units"])}天**　｜　已排休 **{days_text(totals["used_units"])}天**　｜　剩餘 **{days_text(totals["remaining_units"])}天**')
    st.caption(f'來源：星期六{record["saturday_days"]}天＋國定假日／補假{record["holiday_days"]}天；例假不扣額度。已由{record["confirmed_name"]}確認。')
    if totals['remaining_units']<0:
        st.warning('目前已超出本月排休額度；此版本只提醒，不自動禁止送審，請與主管確認。')
    with st.expander('查看排休額度明細'):
        if record['holidays']:
            st.dataframe(pd.DataFrame([{'假日名稱':x['name'],'原假日':date.fromisoformat(x['original_date']),
                '計入日期':date.fromisoformat(x['observed_date'])} for x in record['holidays']]),hide_index=True)
        else:st.caption('本月已確認無額外國定假日／補假額度。')
        if record.get('note'):st.write(record['note'])


def allowance_settings(me,repo,month,data):
    if me.get('role') not in ('manager','admin'):
        st.warning('僅主管或系統管理員可設定排休額度。')
        return
    def stay_on_settings():
        st.session_state['_schedule_force_tab_'+me['id']]='排休額度設定'
    pending=PendingAllowance(st.session_state,repo,me['id'])
    if pending.data:
        st.warning('額度操作尚未確認，請先查核、原碼重試或取消。')
        try:
            with st.container(horizontal=True):
                if st.button('查核額度操作',on_click=stay_on_settings):
                    result=pending.resolve();st.info('查核結果：'+result['state'])
                    if result['state']!='not_found':st.rerun()
                if st.button('原碼重試額度操作',on_click=stay_on_settings):
                    pending.send(pending.data['args']);st.rerun()
                if st.button('取消未確認額度操作',on_click=stay_on_settings):
                    pending.resolve(cancel=True);st.rerun()
        except Exception as exc:st.error(str(exc))
        if pending.data:return
    try:record=repo.allowance_load(month)
    except Exception as exc:
        st.error(f'排休額度讀取失敗：{exc}')
        return
    revision=record['revision'] if record else 0
    with st.container(border=True):
        st.markdown(f'**{month[:7]}｜已核定月排休額度**')
        if record:
            st.markdown(f'已核定可排休 **{days_text(record["total_units"])}天**')
            stamp=pd.to_datetime(record['updated_at'],utc=True).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S')
            st.caption(f'星期六基礎{record["saturday_days"]}天＋國定假日／補假{record["holiday_days"]}天｜核定者：{record["confirmed_name"]}｜核定時間（台灣）：{stamp}｜版本：{revision}')
        else:st.info('本月尚未核定可排休額度；不以0天代替。')
        st.dataframe(pd.DataFrame(allowance_overview(record,data,month)),hide_index=True,width='stretch',
            column_config={k:st.column_config.NumberColumn(format='%.1f') for k in ('已核定可排休（天）','已排休（天）','剩餘額度（天）')})
        st.caption('已排休依目前已儲存班表計算，草稿／待審不代表核准；未建立或未填寫顯示空白。其他請假不扣每月排休額度。')
    prefix=f'allowance_{me["id"]}_{month}_{revision}'
    saturdays=sum(d.weekday()==5 for d in dates_in_month(month))
    st.caption(f'本月星期六基礎額度：{saturdays}天。未確認前不發布月額度；不得把原假日與補假重複填入。')
    st.caption('國定假日若逢週末，只填一筆原日期＋平日補假日期；依計入日期歸屬月份。此處由管理員核對公司適用日曆，不自行推定法定假日。')
    rows=(record or {}).get('holidays',[])
    frame=pd.DataFrame({'假日名稱':pd.Series([x['name'] for x in rows],dtype='string'),
        '原假日':pd.to_datetime([x['original_date'] for x in rows]),
        '計入日期':pd.to_datetime([x['observed_date'] for x in rows])})
    with st.form(prefix):
        edited=st.data_editor(frame,num_rows='dynamic',hide_index=True,key=prefix+'_holidays',
            column_config={'假日名稱':st.column_config.TextColumn(required=True,max_chars=100),
                '原假日':st.column_config.DateColumn(required=True,format='YYYY-MM-DD'),
                '計入日期':st.column_config.DateColumn(required=True,format='YYYY-MM-DD')})
        units=dict(DEDUCT_UNITS)
        note=st.text_input('額度說明／修改原因',value=(record or {}).get('note',''),max_chars=1000)
        confirmed=st.checkbox('已核對本月假日、補假及扣算方式，確認發布本月額度',key=prefix+'_confirm')
        preview=st.form_submit_button('試算額度（不儲存）',on_click=stay_on_settings)
        save=st.form_submit_button('確認本月排休額度',type='primary',on_click=stay_on_settings)
        if preview or save:
            if save and not confirmed:
                st.error('請先勾選核對確認，不會儲存或發布。')
                return
            try:
                entries=[{'name':x['假日名稱'],'original_date':x['原假日'],
                          'observed_date':x['計入日期']} for x in edited.to_dict('records')]
                normalized=normalize_allowance(month,{'holidays':entries,'deduct_units':units,'note':note})
            except Exception as exc:
                st.error(f'額度資料未儲存：{exc}')
                return
            if preview:
                st.info(f'本次修改試算：{days_text(normalized["total_units"])}天，尚未儲存／核定，上方仍為原核定資料。')
                return
            try:
                pending.send({'p_month':month,'p_expected_revision':revision,
                              'p_payload':{k:normalized[k] for k in ('holidays','deduct_units','note')}})
                st.session_state['_allowance_flash']=True
                stay_on_settings()
                st.rerun()
            except Exception as exc:
                st.error(f'額度操作未確認：{exc}。請先查核原操作。')
    if st.session_state.pop('_allowance_flash',False):st.success('本月排休額度已確認，教練可查看。')
