import os
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st
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

@st.cache_resource
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

def login():
    if "user" in st.session_state:
        return st.session_state.user
    st.title("健身房營運管理系統")
    st.caption("請使用已建立的 Email 與密碼登入")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", use_container_width=True)
    if submitted:
        try:
            result = client().auth.sign_in_with_password({"email":email.strip(), "password":password})
            st.session_state.user = result.user
            st.rerun()
        except Exception as exc:
            st.error(f"登入失敗：{exc}")
    st.stop()

def profile(user_id):
    data = rows(client().table("profiles").select("id,display_name,role,active").eq("id",user_id))
    if not data or not data[0]["active"]:
        st.error("帳號尚未啟用或沒有使用者資料，請聯絡主管。")
        st.stop()
    return data[0]

def coach_options():
    data = rows(client().table("profiles").select("id,display_name").eq("active",True).order("display_name"))
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
    allowed = coaches if me["role"]=="manager" else {me["display_name"]:me["id"]}
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
    for x in data: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
    show_table(data,["operation_date","coach_name","classes_held","classes_cancelled","trial_visits","trial_conversions","note"])

def purchase_page(me):
    st.header("課程購買")
    coaches=coach_options(); allowed=coaches if me["role"]=="manager" else {me["display_name"]:me["id"]}
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
    purchases=rows(client().table("purchase_balances").select("purchase_id,member_name,course_name"))
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
    coaches=coach_options(); allowed=coaches if me["role"]=="manager" else {me["display_name"]:me["id"]}
    members=rows(client().table("members").select("id,member_name").eq("active",True).order("member_name"))
    if not members: st.info("請先建立課程購買紀錄。") ; return
    member_map={x["member_name"]:x["id"] for x in members}
    member_name=st.selectbox("會員名稱",list(member_map),index=None,placeholder="輸入或選擇會員")
    if not member_name: return
    balances=rows(client().table("purchase_balances").select("*").eq("member_id",member_map[member_name]).gt("remaining_sessions",0).order("expiry_date"))
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
    for x in history: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
    st.subheader("扣課紀錄"); show_table(history,["usage_date","coach_name","session_seq","deducted_amount","note"])

def dashboard_page(me):
    st.header("主管 Dashboard")
    if me["role"]!="manager": st.warning("此頁僅限主管使用。") ; return
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

def coach_admin_page(me):
    st.header("教練帳號管理")
    if me["role"] != "manager":
        st.warning("此頁僅限主管使用。")
        return
    admin = admin_client()
    if admin is None:
        st.error("尚未設定 SUPABASE_SECRET_KEY，請由系統管理者在 Streamlit Secrets 加入後重新啟動 App。")
        return

    st.subheader("邀請新教練")
    st.caption("系統會寄出 Supabase 邀請信；教練由信件連結完成帳號設定。主管不需代設密碼。")
    with st.form("invite_coach", clear_on_submit=True):
        c1, c2 = st.columns(2)
        display_name = c1.text_input("教練姓名")
        email = c2.text_input("教練 Email")
        invite = st.form_submit_button("寄出邀請")
    if invite:
        name, mail = display_name.strip(), email.strip().lower()
        if not name or not mail or "@" not in mail:
            st.error("請輸入教練姓名與有效的 Email。")
        else:
            try:
                response = admin.auth.admin.invite_user_by_email(mail)
                invited_user = getattr(response, "user", None)
                if invited_user:
                    admin.table("profiles").update({"display_name": name, "role": "coach", "active": True}).eq("id", invited_user.id).execute()
                st.success(f"已寄出邀請給 {name}（{mail}）。")
            except Exception as exc:
                st.error(f"邀請失敗：{exc}")

    st.subheader("現有帳號")
    profiles = rows(client().table("profiles").select("id,display_name,role,active,created_at").order("display_name"))
    if profiles:
        show_table(profiles, ["display_name", "role", "active", "created_at"])
        coach_profiles = [x for x in profiles if x["role"] == "coach"]
        if coach_profiles:
            labels = {x["display_name"]: x for x in coach_profiles}
            with st.form("coach_status"):
                selected_name = st.selectbox("選擇教練", list(labels))
                new_active = st.selectbox("帳號狀態", ["啟用", "停用"])
                update_status = st.form_submit_button("更新狀態")
            if update_status:
                target = labels[selected_name]
                try:
                    client().table("profiles").update({"active": new_active == "啟用"}).eq("id", target["id"]).execute()
                    st.success(f"{selected_name} 已設定為{new_active}。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"更新失敗：{exc}")

user=login(); me=profile(user.id)
with st.sidebar:
    st.title("🏋️ 營運管理")
    st.write(f'{me["display_name"]}｜{"主管" if me["role"]=="manager" else "教練"}')
    pages=["每日營運","課程購買","銷課表"] + (["主管 Dashboard","教練帳號管理"] if me["role"]=="manager" else [])
    page=st.radio("功能",pages)
    if st.button("登出"):
        client().auth.sign_out(); st.session_state.clear(); st.rerun()

try:
    {"每日營運":daily_page,"課程購買":purchase_page,"銷課表":usage_page,"主管 Dashboard":dashboard_page,"教練帳號管理":coach_admin_page}[page](me)
except Exception as exc:
    st.error(f"讀取資料時發生錯誤：{exc}")
