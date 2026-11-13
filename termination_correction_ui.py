"""管理員更正中止：預覽、確認、單一資料庫交易。"""
from datetime import date
from uuid import uuid4

import streamlit as st

from course_query_views import business_today
from termination_preview import preview_termination, render_preview
from termination_reversal_ui import ACK_LABEL


def render_correction_controls(me, records, purchases, names, codes, coaches, api):
    if me.get('role') != 'admin':
        return
    choices = {row['id']: row for row in records if not row.get('reversed_at')}
    pending_key = f"_termination_correction_{me['id']}"
    pending = st.session_state.get(pending_key)
    if pending:
        st.warning('上次更正結果尚未確認。請先查核或以原內容重送。')
        if st.button('重送同一次更正', key='termination_correction_retry'):
            _submit(api, pending_key, pending)
        return
    if not choices:
        st.caption('目前查詢結果沒有可更正的中止。')
        return

    def label(key):
        row = choices[key]
        p = purchases.get(row['purchase_id'], {})
        kind = '逾期中止' if row['termination_type'] == 'expired' else '退費中止'
        return f"{names.get(p.get('member_id'), '')}｜{codes.get(row['purchase_id'], '')}｜{row['termination_date']}｜{kind}"

    selected = st.selectbox('選擇要更正的中止', list(choices), index=None, format_func=label,
                            key='termination_correction_target')
    if st.button('更正中止', disabled=selected not in choices, key='termination_correction_open'):
        _edit(me, choices[selected], label(selected), coaches, api, pending_key)


def _submit(api, pending_key, payload):
    st.session_state[pending_key] = payload
    try:
        data = api.rpc('correct_course_termination', payload).execute().data
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if (not isinstance(data, dict) or data.get('termination_id') != payload['p_termination_id']
                or not data.get('id') or not data.get('reversal_id') or not data.get('posted_on')):
            raise ValueError('未取得完整確認')
    except Exception as exc:
        # 明確的資料庫拒絕已回滾；網路中斷或不完整回應則只能重送原操作。
        if getattr(exc, 'code', None) == 'PGRST202':
            st.session_state.pop(pending_key, None)
            st.error('資料庫尚未安裝更正中止功能，未儲存任何變更。')
        elif getattr(exc, 'code', None) in {'P0001', '42501', '23503', '23505', '23514', '22007'}:
            st.session_state.pop(pending_key, None)
            st.error(f"更正未儲存：{getattr(exc, 'message', '請重新核對資料。')}")
        else:
            st.rerun()
        return
    st.session_state.pop(pending_key, None)
    for key in list(st.session_state):
        if str(key).startswith('_confirmed_query_'):
            st.session_state.pop(key, None)
    st.session_state['_termination_reversal_success'] = '中止已更正。原單、撤銷及更正單均已保留。'
    st.rerun()


@st.dialog('更正中止')
def _edit(me, row, label, coaches, api, pending_key):
    if me.get('role') != 'admin':
        return
    pending = st.session_state.get(pending_key)
    if pending:
        if st.button('重送同一次更正', key='termination_dialog_retry'):
            _submit(api, pending_key, pending)
        return
    prefix = f"correct_termination_{row['id']}"
    st.write(label)
    st.caption('保留原單；撤銷與更正同時儲存，沖回與更正金額都列入更正當日。系統不會自動退款或追回獎金。')
    kind = st.selectbox('更正後類型', ['expired', 'refund'], index=int(row['termination_type']=='refund'),
                        format_func=lambda x: '逾期中止' if x=='expired' else '退費中止', key=prefix+'_kind')
    fee = kind=='refund' and st.checkbox('收取 20% 手續費', value=bool(row.get('charge_fee')), key=prefix+'_fee')
    bonus = kind=='expired' and st.checkbox('計算結單獎金', value=bool(row.get('completion_bonus_eligible')), key=prefix+'_bonus')
    coach = None
    if bonus:
        options = list(coaches)
        original = next((i for i,x in enumerate(options) if coaches[x]==row.get('completion_bonus_coach_id')), None)
        chosen = st.selectbox('結單獎金歸屬教練', options, index=original, key=prefix+'_coach')
        coach = coaches.get(chosen)
    try:
        amounts = preview_termination(row['remaining_amount'], row['remaining_net_amount'], kind, fee)
        render_preview(st, amounts, kind)
    except (ValueError, KeyError, ArithmeticError) as exc:
        st.error(f'無法核對更正金額：{exc}')
        return
    with st.form(prefix, enter_to_submit=False):
        today = business_today()
        term_date = st.date_input('更正後中止日期', value=min(date.fromisoformat(str(row['termination_date'])), today), max_value=today)
        reason = st.text_area('更正原因（必填）', max_chars=1000)
        note = st.text_area('更正後備註', value=row.get('note') or '', max_chars=1000)
        ack = st.checkbox(ACK_LABEL)
        closed = st.checkbox('已確認相關月份的報表；如已交付或結算，已確認更正及對帳方式')
        submitted = st.form_submit_button('確認更正', type='primary')
    if not submitted:
        return
    if not term_date or not reason.strip() or not ack or not closed or (bonus and not coach):
        st.error('請填寫日期、原因、必要教練，並確認款項、獎金及報表處理。')
        return
    _submit(api, pending_key, dict(p_operation_id=str(uuid4()), p_termination_id=row['id'],
        p_termination_date=str(term_date), p_termination_type=kind, p_charge_fee=fee,
        p_completion_bonus_eligible=bonus, p_completion_bonus_coach_id=coach, p_reason=reason.strip(),
        p_note=note.strip() or None, p_settlement_confirmed=True, p_reports_confirmed=True, p_expected_remaining_net=int(amounts[0]),
        p_expected_fee_net=int(amounts[1]), p_expected_refund_net=int(amounts[2])))
