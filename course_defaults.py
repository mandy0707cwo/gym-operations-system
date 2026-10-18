"""課程目錄的選填預設與購課帶入；不連線資料庫、不改寫歷史交易。"""
from decimal import Decimal, InvalidOperation

def catalog_default_payload(sessions, amount, note):
    """沿用購課欄位可接受範圍，未設定一律儲存 NULL。"""
    def decimal_value(value, label):
        try:
            parsed=Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"{label}必須為有效數字。") from exc
        if isinstance(value,bool) or not parsed.is_finite():
            raise ValueError(f"{label}必須為有效數字。")
        return parsed
    if sessions is not None:
        value=decimal_value(sessions,"課程堂數")
        if value!=value.to_integral_value() or not 1<=value<=999:
            raise ValueError("課程堂數須為 1 至 999 的整數；未設定請留白。")
        sessions=int(value)
    if amount is not None:
        value=decimal_value(amount,"成交總金額")
        if not 0<value<=10000000 or value!=value.quantize(Decimal("0.01")):
            raise ValueError("成交總金額須大於 0、最多 10,000,000 且至多兩位小數；未設定請留白。")
        amount=float(value)
    return {"default_sessions":sessions,"default_total_amount":amount,"note":str(note or "").strip() or None}

def combined_purchase_note(member_note, course_note):
    """客戶備註在前、課程備註在後，分行保留；空白來源不新增文字。"""
    return "\n".join(text for note in (member_note,course_note) if (text:=str(note or "").strip()))

def apply_purchase_catalog_defaults(state, revision, course, member):
    """只在選擇來源變動時帶入，避免一般重新執行覆蓋人工修改。"""
    course=course or {}
    member=member or {}
    course_source=course.get("id") or course.get("course_name") or "none"
    course_marker=f"purchase_default_course_source_{revision}"
    if state.get(course_marker)!=course_source:
        state[f"purchase_sessions_{revision}"]=course.get("default_sessions")
        amount=course.get("default_total_amount")
        state[f"purchase_amount_{revision}"]=float(amount) if amount is not None else None
        state[course_marker]=course_source
    member_id=member.get("id") or "none"
    note_marker=f"purchase_default_note_source_{revision}"
    note_source=(member_id,course_source)
    if state.get(note_marker)!=note_source:
        state[f"purchase_note_{revision}_{member_id}"]=combined_purchase_note(member.get("note"),course.get("note"))
        state[note_marker]=note_source

