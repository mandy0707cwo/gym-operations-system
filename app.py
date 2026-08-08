import os
import re
from io import BytesIO
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from supabase import create_client
from supabase.lib.client_options import ClientOptions

load_dotenv()
st.set_page_config(page_title="健身房營運管理", page_icon="🏋️", layout="wide")

LABELS = {
    "operation_date":"日期", "coach_name":"教練", "classes_held":"上課堂數",
    "classes_cancelled":"取消堂數", "trial_visits":"體驗人次",
    "trial_conversions":"體驗成交人次", "member_name":"會員名稱",
    "course_name":"課程名稱", "total_sessions":"原始堂數",
    "remaining_sessions":"剩餘堂數", "remaining_amount":"剩餘金額",
    "usage_date":"銷課日期", "session_seq":"第幾堂", "deducted_amount":"扣課金額",
}
ROLE_LABELS = {"coach": "教練", "manager": "主管", "admin": "系統管理員"}
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")

def username_email(username):
    return f"{username.lower()}@gym-users.example.com"

def secret(name):
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""

def client():
    """每個 Streamlit 使用者連線使用獨立 Supabase Auth session，避免帳號互相沿用。"""
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error("尚未設定 SUPABASE_URL 與 SUPABASE_ANON_KEY。請依 README 完成設定。")
        st.stop()
    if "_supabase_client" not in st.session_state:
        st.session_state._supabase_client = create_client(url, key)
    return st.session_state._supabase_client

def admin_client():
    """僅供主管邀請帳號；Secret key 只存在 Streamlit 伺服器端。"""
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SECRET_KEY")
    if not key:
        return None
    return create_client(
        url,
        key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )

def rows(query):
    return query.execute().data or []

def collapse_sidebar_on_mobile():
    """手機版切換頁面後自動收合側邊選單，桌面版不受影響。"""
    components.html(
        """
        <script>
        (() => {
          if (window.parent.innerWidth > 768) return;
          const doc = window.parent.document;
          const closeButton = doc.querySelector(
            '[data-testid="stSidebarCollapseButton"] button, button[kind="header"]'
          );
          const sidebar = doc.querySelector('[data-testid="stSidebar"]');
          if (sidebar && closeButton && sidebar.getBoundingClientRect().width > 0) {
            setTimeout(() => closeButton.click(), 120);
          }
        })();
        </script>
        """,
        height=0,
        width=0,
    )

def login():
    if "user" in st.session_state:
        return st.session_state.user
    st.title("健身房營運管理系統")
    st.caption("請使用系統管理員建立的帳號與密碼登入")
    with st.form("login"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", use_container_width=True)
    if submitted:
        try:
            login_name = username.strip().lower()
            # 保留既有管理員 Email 一次過渡登入；新帳號一律使用系統帳號。
            email = login_name if "@" in login_name else username_email(login_name)
            result = client().auth.sign_in_with_password({"email":email, "password":password})
            st.session_state.user = result.user
            st.rerun()
        except Exception as exc:
            st.error(f"登入失敗：{exc}")
    st.stop()

def profile(user_id):
    data = rows(client().table("profiles").select("id,username,display_name,role,active").eq("id",user_id))
    if not data or not data[0]["active"]:
        st.error("帳號尚未啟用或沒有使用者資料，請聯絡主管。")
        st.stop()
    return data[0]

def coach_options():
    data = rows(client().table("profiles").select("id,display_name,role").eq("active",True).order("display_name"))
    data = [x for x in data if x.get("role") in ("coach", "manager")]
    return {x["display_name"]:x["id"] for x in data}

def show_table(data, columns=None):
    df = pd.DataFrame(data)
    if df.empty:
        st.info("目前沒有符合條件的資料。")
        return
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    st.dataframe(df.rename(columns=LABELS), use_container_width=True, hide_index=True)

def daily_page(me):
    st.header("每日營運")
    coaches = coach_options()
    allowed = coaches if me["role"] in ("manager","admin") else {me["display_name"]:me["id"]}
    with st.form("daily"):
        c1,c2 = st.columns(2)
        op_date = c1.date_input("日期", date.today())
        coach_name = c2.selectbox("教練", list(allowed))
        c1,c2,c3,c4 = st.columns(4)
        held = c1.number_input("每日上課堂數",0,100,0)
        cancelled = c2.number_input("上課取消堂數",0,100,0)
        trials = c3.number_input("體驗人次",0,100,0)
        converted = c4.number_input("體驗成交人次",0,100,0)
        note = st.text_area("備註")
        save = st.form_submit_button("儲存")
    if save:
        if converted > trials:
            st.error("體驗成交人次不可大於體驗人次。")
        else:
            payload={"operation_date":str(op_date),"coach_id":allowed[coach_name],"classes_held":held,
                     "classes_cancelled":cancelled,"trial_visits":trials,"trial_conversions":converted,"note":note or None}
            try:
                client().table("daily_operations").upsert(payload,on_conflict="operation_date,coach_id").execute()
                st.success("每日營運資料已儲存；同日同教練資料會更新而非重複新增。")
            except Exception as exc: st.error(f"儲存失敗：{exc}")
    data=rows(client().table("daily_operations").select("operation_date,coach_id,classes_held,classes_cancelled,trial_visits,trial_conversions,note").order("operation_date",desc=True).limit(100))
    names={v:k for k,v in coaches.items()}
    data=[x for x in data if x.get("coach_id") in names]
    for x in data: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
    show_table(data,["operation_date","coach_name","classes_held","classes_cancelled","trial_visits","trial_conversions","note"])

def purchase_page(me):
    st.header("課程購買")
    coaches=coach_options(); allowed=coaches if me["role"] in ("manager","admin") else {me["display_name"]:me["id"]}
    with st.form("purchase"):
        c1,c2,c3=st.columns(3)
        member_name=c1.text_input("會員名稱（需完整一致）")
        kind=c2.selectbox("購買類型",["首次購買","續課"])
        coach_name=c3.selectbox("指導教練",list(allowed))
        c1,c2,c3=st.columns(3)
        course=c1.text_input("課程名稱")
        sessions=c2.number_input("課程堂數",1,999,1)
        amount=c3.number_input("成交總金額",0.0,10000000.0,step=100.0,format="%.2f")
        c1,c2,c3=st.columns(3)
        purchased=c1.date_input("購買日期",date.today())
        expiry=c2.date_input("有效日期",date.today()+timedelta(days=365))
        plan=c3.selectbox("付款方式",["未分期","分期"])
        count=st.selectbox("總期數",[2,3],disabled=plan=="未分期") if plan=="分期" else 1
        c1,c2,c3=st.columns(3)
        installment_no=c1.selectbox("此次為第幾期",list(range(1,count+1)))
        paid=c2.number_input("此次支付金額",0.0,10000000.0,step=100.0,format="%.2f")
        paid_date=c3.date_input("支付日期",purchased)
        save=st.form_submit_button("建立購買紀錄")
    if save:
        errors=[]
        if not member_name.strip(): errors.append("會員名稱不可空白")
        if not course.strip(): errors.append("課程名稱不可空白")
        if expiry<purchased: errors.append("有效日期不可早於購買日期")
        if paid<=0: errors.append("此次支付金額須大於 0")
        if paid>amount: errors.append("此次支付金額不可大於成交總金額")
        if installment_no!=1: errors.append("新購買紀錄應先登錄第 1 期；後續期款請由付款功能登錄")
        if errors: st.error("；".join(errors))
        else:
            try:
                member=rows(client().table("members").select("id").eq("member_name",member_name.strip()))
                if member: member_id=member[0]["id"]
                else:
                    member_id=rows(client().table("members").insert({"member_name":member_name.strip(),"created_by":me["id"]}))[0]["id"]
                p=rows(client().table("purchases").insert({"member_id":member_id,"purchase_kind":"first" if kind=="首次購買" else "renewal",
                    "coach_id":allowed[coach_name],"course_name":course.strip(),"total_sessions":sessions,"total_amount":amount,
                    "purchase_date":str(purchased),"expiry_date":str(expiry),"payment_plan":"full" if plan=="未分期" else "installment",
                    "installment_count":count,"created_by":me["id"]}))[0]
                client().table("purchase_payments").insert({"purchase_id":p["id"],"installment_no":1,"amount":paid,"paid_date":str(paid_date),"created_by":me["id"]}).execute()
                st.success("購買與首期付款紀錄已建立。")
            except Exception as exc: st.error(f"建立失敗：{exc}")
    st.subheader("登錄後續期款")
    purchases=rows(client().table("purchase_balances").select("purchase_id,member_name,course_name,coach_id"))
    operational_ids=set(coaches.values())
    purchases=[x for x in purchases if x.get("coach_id") in operational_ids]
    lookup={f'{x["member_name"]}｜{x["course_name"]}｜{x["purchase_id"][:8]}':x["purchase_id"] for x in purchases}
    if lookup:
        with st.form("payment"):
            label=st.selectbox("購買紀錄",list(lookup))
            c1,c2,c3=st.columns(3)
            no=c1.selectbox("期次",[1,2,3]); pay_amount=c2.number_input("支付金額",0.01,10000000.0,step=100.0); pay_date=c3.date_input("付款日期",date.today())
            add=st.form_submit_button("新增付款")
        if add:
            try:
                client().table("purchase_payments").insert({"purchase_id":lookup[label],"installment_no":no,"amount":pay_amount,"paid_date":str(pay_date),"created_by":me["id"]}).execute()
                st.success("付款紀錄已新增。")
            except Exception as exc: st.error(f"新增失敗（請檢查期次是否重複或超出設定）：{exc}")

def usage_page(me):
    st.header("銷課表")
    coaches=coach_options(); allowed=coaches if me["role"] in ("manager","admin") else {me["display_name"]:me["id"]}
    members=rows(client().table("members").select("id,member_name").eq("active",True).order("member_name"))
    if not members: st.info("請先建立課程購買紀錄。") ; return
    member_map={x["member_name"]:x["id"] for x in members}
    member_name=st.selectbox("會員名稱",list(member_map),index=None,placeholder="輸入或選擇會員")
    if not member_name: return
    balances=rows(client().table("purchase_balances").select("*").eq("member_id",member_map[member_name]).gt("remaining_sessions",0).order("expiry_date"))
    balances=[x for x in balances if x.get("coach_id") in set(coaches.values())]
    show_table(balances,["course_name","coach_name","total_sessions","used_sessions","remaining_sessions","remaining_amount","expiry_date","status"])
    active=[x for x in balances if x["status"]=="active"]
    if not active: st.warning("此會員沒有可扣課的有效課程。") ; return
    lookup={f'{x["course_name"]}｜剩 {x["remaining_sessions"]} 堂｜餘額 {x["remaining_amount"]}':x for x in active}
    with st.form("consume"):
        label=st.selectbox("選擇課程",list(lookup)); selected=lookup[label]
        c1,c2=st.columns(2); usage_date=c1.date_input("銷課日期",date.today()); coach=c2.selectbox("授課教練",list(allowed))
        note=st.text_input("備註"); submit=st.form_submit_button("確認扣除 1 堂")
    per=Decimal(str(selected["remaining_amount"])) if selected["remaining_sessions"]==1 else (Decimal(str(selected["total_amount"]))/selected["total_sessions"]).quantize(Decimal("0.01"))
    st.caption(f"本次預計扣除：1 堂／TWD {per:,.2f}；最後一堂會自動扣完剩餘金額。")
    if submit:
        try:
            client().rpc("consume_session",{"p_purchase_id":selected["purchase_id"],"p_usage_date":str(usage_date),"p_coach_id":allowed[coach],"p_note":note}).execute()
            st.success("扣課完成。") ; st.rerun()
        except Exception as exc: st.error(f"扣課失敗：{exc}")
    history=rows(client().table("session_usages").select("usage_date,coach_id,session_seq,deducted_amount,note").eq("purchase_id",selected["purchase_id"]).order("session_seq",desc=True))
    names={v:k for k,v in coaches.items()}
    history=[x for x in history if x.get("coach_id") in names]
    for x in history: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
    st.subheader("扣課紀錄"); show_table(history,["usage_date","coach_name","session_seq","deducted_amount","note"])

def dashboard_page(me):
    st.header("主管 Dashboard")
    if me["role"] not in ("manager","admin"): st.warning("此頁僅限主管與系統管理員使用。") ; return
    coaches=coach_options(); c1,c2,c3=st.columns(3)
    start=c1.date_input("開始日期",date.today().replace(day=1)); end=c2.date_input("結束日期",date.today())
    selected=c3.multiselect("教練",list(coaches),default=list(coaches))
    if start>end: st.error("開始日期不可晚於結束日期。") ; return
    ids=[coaches[x] for x in selected]
    ops=rows(client().table("daily_operations").select("*").gte("operation_date",str(start)).lte("operation_date",str(end)))
    purchases=rows(client().table("purchases").select("coach_id,total_sessions,total_amount,purchase_date").gte("purchase_date",str(start)).lte("purchase_date",str(end)))
    names={v:k for k,v in coaches.items()}; result=[]
    for cid in ids:
        o=[x for x in ops if x["coach_id"]==cid]; p=[x for x in purchases if x["coach_id"]==cid]
        held=sum(x["classes_held"] for x in o); cancelled=sum(x["classes_cancelled"] for x in o)
        trials=sum(x["trial_visits"] for x in o); converted=sum(x["trial_conversions"] for x in o)
        sessions=sum(x["total_sessions"] for x in p); amount=sum(float(x["total_amount"]) for x in p)
        result.append({"教練":names[cid],"上課堂數":held,"取消率":cancelled/(held+cancelled) if held+cancelled else None,
                       "體驗成交率":converted/trials if trials else None,"成交堂數":sessions,"成交金額":amount,
                       "平均每堂單價":amount/sessions if sessions else None})
    df=pd.DataFrame(result)
    if df.empty: st.info("沒有可顯示的資料。") ; return
    totals=df[["上課堂數","成交堂數","成交金額"]].sum()
    a,b,c=st.columns(3); a.metric("上課堂數",f'{totals["上課堂數"]:,.0f}'); b.metric("成交堂數",f'{totals["成交堂數"]:,.0f}'); c.metric("成交金額",f'TWD {totals["成交金額"]:,.0f}')
    display_df=df.copy()
    display_df["取消率"]=display_df["取消率"]*100
    display_df["體驗成交率"]=display_df["體驗成交率"]*100
    st.dataframe(display_df,hide_index=True,use_container_width=True,column_config={"取消率":st.column_config.NumberColumn(format="%.1f%%"),"體驗成交率":st.column_config.NumberColumn(format="%.1f%%"),"成交金額":st.column_config.NumberColumn(format="TWD %.0f"),"平均每堂單價":st.column_config.NumberColumn(format="TWD %.0f")})
    left,right=st.columns(2)
    left.plotly_chart(px.bar(df,x="教練",y=["上課堂數","成交堂數"],barmode="group",title=f"教練堂數比較（{start} 至 {end}）",labels={"value":"堂數","variable":"指標"}),use_container_width=True)
    right.plotly_chart(px.bar(df,x="教練",y="成交金額",title=f"成交金額（{start} 至 {end}）",labels={"成交金額":"TWD"}),use_container_width=True)

def account_admin_page(me):
    st.header("帳號與權限管理")
    if me["role"] != "admin":
        st.warning("此頁僅限系統管理員使用。")
        return
    admin = admin_client()
    if admin is None:
        st.error("尚未設定 SUPABASE_SECRET_KEY，請由系統管理者在 Streamlit Secrets 加入後重新啟動 App。")
        return

    if not me.get("username"):
        st.warning("目前管理員仍使用舊 Email 登入。請先設定管理員系統帳號；完成後會登出，之後改用新帳號登入。")
        with st.form("convert_admin"):
            new_username = st.text_input("管理員新帳號").strip().lower()
            convert = st.form_submit_button("轉換管理員登入帳號")
        if convert:
            if not USERNAME_RE.fullmatch(new_username):
                st.error("帳號須為 3–30 個小寫英文字母、數字或底線。")
            else:
                try:
                    admin.auth.admin.update_user_by_id(me["id"], {"email": username_email(new_username), "email_confirm": True})
                    admin.table("profiles").update({"username": new_username}).eq("id", me["id"]).execute()
                    client().auth.sign_out(); st.session_state.clear()
                    st.success("管理員帳號已轉換，請使用新帳號登入。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"轉換失敗：{exc}")

    st.subheader("建立新帳號")
    with st.form("create_account", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_account = c1.text_input("登入帳號").strip().lower()
        display_name = c2.text_input("顯示姓名").strip()
        c1, c2 = st.columns(2)
        new_password = c1.text_input("初始密碼（至少 8 碼）", type="password")
        role_label = c2.selectbox("權限", ["教練", "主管", "系統管理員"])
        create_account = st.form_submit_button("建立帳號")
    if create_account:
        role_value = {"教練":"coach", "主管":"manager", "系統管理員":"admin"}[role_label]
        if not USERNAME_RE.fullmatch(new_account):
            st.error("帳號須為 3–30 個小寫英文字母、數字或底線。")
        elif not display_name:
            st.error("顯示姓名不可空白。")
        elif len(new_password) < 8:
            st.error("密碼至少需要 8 碼。")
        else:
            try:
                response = admin.auth.admin.create_user({"email":username_email(new_account), "password":new_password,
                    "email_confirm":True, "user_metadata":{"username":new_account,"display_name":display_name}})
                created_user = getattr(response, "user", None)
                if not created_user: raise RuntimeError("Supabase 未回傳新使用者")
                admin.table("profiles").update({"username":new_account,"display_name":display_name,"role":role_value,"active":True}).eq("id",created_user.id).execute()
                st.success(f"已建立帳號 {new_account}（{role_label}）。")
            except Exception as exc:
                st.error(f"建立失敗：{exc}")

    st.subheader("現有帳號")
    profiles = rows(admin.table("profiles").select("id,username,display_name,role,active,created_at").order("display_name"))
    if profiles:
        table_rows=[{**x,"role":ROLE_LABELS.get(x["role"],x["role"])} for x in profiles]
        show_table(table_rows, ["username", "display_name", "role", "active", "created_at"])
        labels = {f'{x["display_name"]}｜{x.get("username") or "尚未轉換"}': x for x in profiles}
        with st.form("account_update"):
            selected_name = st.selectbox("選擇帳號", list(labels))
            new_role_label = st.selectbox("權限", ["教練", "主管", "系統管理員"])
            new_active = st.selectbox("帳號狀態", ["啟用", "停用"])
            reset_password = st.text_input("重設密碼（留空表示不變；至少 8 碼）", type="password")
            update_status = st.form_submit_button("更新帳號")
        if update_status:
            target = labels[selected_name]
            if target["id"] == me["id"] and new_active == "停用":
                st.error("不可停用目前登入的管理員帳號。")
            elif reset_password and len(reset_password) < 8:
                st.error("重設密碼至少需要 8 碼。")
            else:
                try:
                    role_value={"教練":"coach","主管":"manager","系統管理員":"admin"}[new_role_label]
                    admin.table("profiles").update({"role":role_value,"active":new_active=="啟用"}).eq("id",target["id"]).execute()
                    if reset_password: admin.auth.admin.update_user_by_id(target["id"], {"password":reset_password})
                    st.success("帳號與權限已更新。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"更新失敗：{exc}")

def _excel_bytes(sheet_frames):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        for sheet_name, frame in sheet_frames.items():
            safe_name = sheet_name[:31]
            frame.to_excel(writer, sheet_name=safe_name, index=False)
            worksheet = writer.sheets[safe_name]
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, max(len(frame), 1), max(len(frame.columns) - 1, 0))
            for col_no, column in enumerate(frame.columns):
                values = frame[column].fillna("").astype(str) if not frame.empty else pd.Series(dtype=str)
                width = min(max([len(str(column))] + values.map(len).tolist()) + 2, 32)
                worksheet.set_column(col_no, col_no, width)
    return output.getvalue()

def data_io_page(me):
    st.header("資料匯入／匯出")
    if me["role"] != "admin":
        st.warning("此頁僅限系統管理員使用。")
        return
    admin = admin_client()
    if admin is None:
        st.error("尚未設定 SUPABASE_SECRET_KEY。")
        return

    st.subheader("匯出 Excel 報表")
    c1, c2 = st.columns(2)
    start = c1.date_input("開始日期", date.today().replace(day=1), key="export_start")
    end = c2.date_input("結束日期", date.today(), key="export_end")
    profiles = rows(admin.table("profiles").select("id,username,display_name,role,active").order("display_name"))
    operational_profiles = [x for x in profiles if x["role"] in ("coach", "manager")]
    coach_map = {x["display_name"]: x["id"] for x in operational_profiles}
    selected_coaches = st.multiselect("教練（未選擇代表全部）", list(coach_map), key="export_coaches")

    if start > end:
        st.error("開始日期不可晚於結束日期。")
    else:
        coach_ids = {coach_map[x] for x in selected_coaches}
        operational_ids = set(coach_map.values())
        id_to_name = {x["id"]: x["display_name"] for x in operational_profiles}
        members = rows(admin.table("members").select("*").order("member_name"))
        operations = rows(admin.table("daily_operations").select("*").gte("operation_date", str(start)).lte("operation_date", str(end)).order("operation_date"))
        purchases = rows(admin.table("purchases").select("*").gte("purchase_date", str(start)).lte("purchase_date", str(end)).order("purchase_date"))
        usages = rows(admin.table("session_usages").select("*").gte("usage_date", str(start)).lte("usage_date", str(end)).order("usage_date"))
        purchase_ids = {x["id"] for x in purchases}
        payments = rows(admin.table("purchase_payments").select("*").gte("paid_date", str(start)).lte("paid_date", str(end)).order("paid_date"))
        effective_ids = coach_ids or operational_ids
        operations = [x for x in operations if x.get("coach_id") in effective_ids]
        purchases = [x for x in purchases if x.get("coach_id") in effective_ids]
        purchase_ids = {x["id"] for x in purchases}
        usages = [x for x in usages if x.get("coach_id") in effective_ids]
        payments = [x for x in payments if x.get("purchase_id") in purchase_ids]
        for collection in (operations, purchases, usages):
            for item in collection:
                if "coach_id" in item:
                    item["coach_name"] = id_to_name.get(item["coach_id"], "")
        report = _excel_bytes({
            "會員名單": pd.DataFrame(members),
            "每日營運": pd.DataFrame(operations),
            "課程購買": pd.DataFrame(purchases),
            "付款紀錄": pd.DataFrame(payments),
            "銷課紀錄": pd.DataFrame(usages),
            "帳號權限": pd.DataFrame(operational_profiles),
        })
        st.download_button("下載 Excel 報表", report,
            file_name=f"健身房營運報表_{start}_{end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)

    st.divider()
    st.subheader("匯入 Excel")
    st.caption("目前支援會員名單與每日營運。系統會先檢查整份檔案；有錯誤時不會寫入資料庫。")
    member_template = pd.DataFrame(columns=["member_name", "active"])
    operation_template = pd.DataFrame(columns=["operation_date", "coach_username", "classes_held", "classes_cancelled", "trial_visits", "trial_conversions", "note"])
    template = _excel_bytes({"會員名單": member_template, "每日營運": operation_template})
    st.download_button("下載匯入範本", template, file_name="健身房資料匯入範本.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    uploaded = st.file_uploader("選擇填妥的 Excel 範本", type=["xlsx"])
    if uploaded is not None:
        try:
            workbook = pd.ExcelFile(uploaded)
            allowed_sheets = [x for x in ("會員名單", "每日營運") if x in workbook.sheet_names]
            if not allowed_sheets:
                st.error("檔案必須至少包含「會員名單」或「每日營運」工作表。")
                return
            errors = []
            member_df = pd.read_excel(workbook, "會員名單") if "會員名單" in allowed_sheets else pd.DataFrame()
            op_df = pd.read_excel(workbook, "每日營運") if "每日營運" in allowed_sheets else pd.DataFrame()
            required_members = {"member_name", "active"}
            required_ops = {"operation_date", "coach_username", "classes_held", "classes_cancelled", "trial_visits", "trial_conversions", "note"}
            if not member_df.empty and not required_members.issubset(member_df.columns):
                errors.append("會員名單欄位不完整。")
            if not op_df.empty and not required_ops.issubset(op_df.columns):
                errors.append("每日營運欄位不完整。")
            username_map = {x.get("username"): x["id"] for x in profiles if x.get("username")}
            clean_members, clean_ops = [], []
            if not errors:
                for index, item in member_df.fillna("").iterrows():
                    name = str(item["member_name"]).strip()
                    if not name:
                        errors.append(f"會員名單第 {index + 2} 列：會員名稱不可空白。")
                    else:
                        active_value = str(item["active"]).strip().lower()
                        clean_members.append({"member_name": name, "active": active_value not in ("false", "0", "否", "停用")})
                for index, item in op_df.fillna("").iterrows():
                    try:
                        op_date = pd.to_datetime(item["operation_date"]).date()
                        username = str(item["coach_username"]).strip().lower()
                        counts = {key: int(item[key]) for key in ("classes_held", "classes_cancelled", "trial_visits", "trial_conversions")}
                        if username not in username_map:
                            raise ValueError("找不到教練帳號")
                        if any(value < 0 for value in counts.values()):
                            raise ValueError("人次與堂數不可為負數")
                        if counts["trial_conversions"] > counts["trial_visits"]:
                            raise ValueError("體驗成交人次不可大於體驗人次")
                        clean_ops.append({"operation_date": str(op_date), "coach_id": username_map[username], **counts,
                            "note": str(item["note"]).strip() or None})
                    except Exception as exc:
                        errors.append(f"每日營運第 {index + 2} 列：{exc}")
            if errors:
                st.error("匯入檢查未通過：\n- " + "\n- ".join(errors[:20]))
            else:
                st.success(f"檢查通過：會員 {len(clean_members)} 筆、每日營運 {len(clean_ops)} 筆。")
                if st.button("確認匯入資料庫", type="primary"):
                    for item in clean_members:
                        existing = rows(admin.table("members").select("id").eq("member_name", item["member_name"]))
                        if existing:
                            admin.table("members").update({"active": item["active"]}).eq("id", existing[0]["id"]).execute()
                        else:
                            admin.table("members").insert({**item, "created_by": me["id"]}).execute()
                    for item in clean_ops:
                        admin.table("daily_operations").upsert(item, on_conflict="operation_date,coach_id").execute()
                    st.success("資料匯入完成。")
        except Exception as exc:
            st.error(f"無法讀取或匯入檔案：{exc}")

user=login(); me=profile(user.id)
with st.sidebar:
    st.title("🏋️ 營運管理")
    st.write(f'{me["display_name"]}｜{ROLE_LABELS.get(me["role"],me["role"])}')
    pages=["每日營運","課程購買","銷課表"]
    if me["role"] in ("manager","admin"): pages.append("主管 Dashboard")
    if me["role"] == "admin":
        pages.extend(["帳號與權限管理", "資料匯入／匯出"])
    page=st.radio("功能",pages)
    if st.button("登出"):
        client().auth.sign_out(); st.session_state.clear(); st.rerun()

collapse_sidebar_on_mobile()

try:
    {"每日營運":daily_page,"課程購買":purchase_page,"銷課表":usage_page,"主管 Dashboard":dashboard_page,"帳號與權限管理":account_admin_page,"資料匯入／匯出":data_io_page}[page](me)
except Exception as exc:
    st.error(f"讀取資料時發生錯誤：{exc}")
