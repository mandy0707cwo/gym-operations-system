"""管理員的撤銷中止確認；只透過單一原子 RPC，不在畫面直接更改狀態。"""
from copy import deepcopy
from uuid import uuid4
import streamlit as st

ACK_LABEL = '已確認未實際退款、相關獎金未發放；若已付款，已另行完成款項處理'


def render_reversal_controls(me, records, purchase_map, member_names, purchase_codes, api):
    if me.get('role') != 'admin':
        return
    choices = {x['id']: x for x in records if not x.get('reversed_at')}
    if not choices:
        st.caption('目前查詢結果沒有可撤銷的中止。')
        return

    def label(key):
        row = choices[key]
        purchase = purchase_map.get(row['purchase_id'], {})
        kind = '逾期中止' if row['termination_type'] == 'expired' else '退費中止'
        return f"{member_names.get(purchase.get('member_id'), '')}｜{purchase_codes.get(row['purchase_id'], '')}｜{row['termination_date']}｜{kind}"

    target = st.selectbox('選擇要撤銷的中止', list(choices), index=None, format_func=label,
                          placeholder='請選擇上方中止記錄', key='termination_reversal_target')
    if st.button('撤銷中止', disabled=target not in choices, key='termination_reversal_open'):
        st.session_state['_termination_reversal_dialog']={'actor':me['id'],'target':target}
    opened=st.session_state.get('_termination_reversal_dialog',{})
    if opened.get('actor')==me['id'] and opened.get('target') in choices:
        target=opened['target']
        _confirm_reversal(me, deepcopy(choices[target]), label(target), api)


def _dismiss_reversal():
    st.session_state.pop('_termination_reversal_dialog',None)


@st.dialog('撤銷中止',on_dismiss=_dismiss_reversal)
def _confirm_reversal(me, row, label, api):
    if me.get('role') != 'admin':
        st.error('僅系統管理員可撤銷中止。')
        return
    key = f"_termination_reversal_{me['id']}_{row['id']}"
    pending = st.session_state.setdefault(key, {'operation_id': str(uuid4()), 'payload': None})
    st.write(label)
    st.write('會保留原中止記錄並新增撤銷記錄；不延長課程效期，也不會自動收回退款或已發獎金。')
    st.caption('撤銷日期由系統記錄為今日；沖回列在撤銷日期，不覆寫以前月份。')
    if st.button('取消',key='termination_reversal_cancel'):
        _dismiss_reversal();st.rerun()
    saved = pending['payload'] or {}
    with st.form(f"termination_reversal_form_{row['id']}", enter_to_submit=False):
        reason = st.text_area('撤銷原因', value=saved.get('p_reason', ''), max_chars=1000)
        ack = st.checkbox(ACK_LABEL, value=saved.get('p_settlement_confirmed', False))
        submitted = st.form_submit_button('確認撤銷', type='primary')
    if not submitted:
        return
    if not reason.strip() or not ack:
        st.error('請填寫撤銷原因並確認款項及獎金處理。')
        return
    payload = {'p_operation_id': pending['operation_id'], 'p_termination_id': row['id'],
               'p_reason': reason.strip(), 'p_settlement_confirmed': True}
    if pending['payload'] is not None and pending['payload'] != payload:
        st.error('上次送出結果尚未確認，請使用原原因重試，勿更換操作內容。')
        return
    pending['payload'] = deepcopy(payload)
    try:
        data = api.rpc('reverse_course_termination', payload).execute().data
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict) or data.get('termination_id') != row['id'] or not data.get('id'):
            raise ValueError('未取得完整撤銷確認')
    except Exception as exc:
        st.warning(f'撤銷結果尚未確認，請保留原內容重試；同一次操作不會重複沖回。{exc}')
        return
    st.session_state.pop(key, None)
    _dismiss_reversal()
    for cache_key in list(st.session_state):
        if str(cache_key).startswith('_confirmed_query_'):
            st.session_state.pop(cache_key,None)
    st.session_state['_termination_reversal_success'] = '中止已撤銷；原紀錄及原因已保留，未延長效期。'
    st.rerun()
