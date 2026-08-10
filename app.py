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
    "classes_cancelled":"銷課取消堂數", "trial_visits":"體驗人次",
    "trial_conversions":"體驗成交人次", "member_name":"會員名稱",
    "trial_member_name":"體驗會員姓名",
    "course_name":"課程名稱", "total_sessions":"原始堂數", "session_hours":"每堂課時數",
    "remaining_sessions":"剩餘堂數", "remaining_amount":"剩餘金額",
    "usage_date":"銷課日期", "session_seq":"第幾堂", "deducted_amount":"扣課金額",
    "entry_date":"日期", "content":"內容", "hours":"時數",
    "deducted_hours":"應扣除時間", "deduction_reason":"扣除原因",
    "cancel_date":"取消日期", "cancelled_sessions":"銷課取消堂數", "reason":"取消原因",
}
ROLE_LABELS = {"coach": "教練", "shared_coach": "共用教練帳號", "manager": "主管", "admin": "系統管理員"}
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
    display_df=df.rename(columns=LABELS)
    money_columns={LABELS.get(x,x) for x in ("total_amount","remaining_amount","deducted_amount","amount")}
    money_config={x:st.column_config.NumberColumn(format="TWD %.0f") for x in money_columns if x in display_df.columns}
    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=money_config)

def daily_page(me):
    st.header("每日營運")
    coaches = coach_options()
    allowed = coaches if me["role"] in ("shared_coach","manager","admin") else {me["display_name"]:me["id"]}
    names={v:k for k,v in coaches.items()}
    tab1,tab2,tab3=st.tabs(["體驗項目","單堂銷售","活動支援"])

    def standard_entry(tab, table_name, form_key, content_label, catalog_type, require_member=False):
        with tab:
            catalog=rows(client().table("operation_item_catalog").select("item_name").eq("item_type",catalog_type).order("item_name"))
            item_names=[x["item_name"] for x in catalog]
            if not item_names:
                st.warning(f"尚未建立{content_label}選項，請由系統管理員到「資料管理」新增。")
                return
            with st.form(form_key,clear_on_submit=True):
                c1,c2=st.columns(2); entry_date=c1.date_input("日期",date.today()); coach_name=c2.selectbox("教練",list(allowed))
                member_name=st.text_input("體驗會員姓名") if require_member else None
                c1,c2=st.columns(2); content=c1.selectbox(content_label,item_names); hours=c2.number_input("時數",0.25,24.0,1.0,step=0.25)
                save=st.form_submit_button("新增紀錄")
            if save:
                if require_member and not member_name.strip():
                    st.error("體驗會員姓名不可空白。")
                else:
                    try:
                        payload={"entry_date":str(entry_date),"content":content,"hours":hours,"coach_id":allowed[coach_name],"created_by":me["id"]}
                        if require_member: payload["member_name"]=member_name.strip()
                        client().table(table_name).insert(payload).execute()
                        st.success("紀錄已新增。"); st.rerun()
                    except Exception as exc: st.error(f"新增失敗：{exc}")
            select_fields="entry_date,content,hours,coach_id,member_name" if require_member else "entry_date,content,hours,coach_id"
            data=rows(client().table(table_name).select(select_fields).order("entry_date",desc=True).limit(100))
            data=[x for x in data if x.get("coach_id") in names]
            for x in data:
                x["coach_name"]=names.get(x.pop("coach_id"),"未知")
                if require_member: x["trial_member_name"]=x.pop("member_name",None)
            columns=["entry_date"] + (["trial_member_name"] if require_member else []) + ["content","hours","coach_name"]
            show_table(data,columns)

    standard_entry(tab1,"trial_items","trial_item_form","體驗內容","trial",require_member=True)
    standard_entry(tab2,"single_sales","single_sale_form","銷售內容","single_sale")
    with tab3:
        with st.form("event_support_form",clear_on_submit=True):
            c1,c2=st.columns(2); entry_date=c1.date_input("日期",date.today(),key="event_date"); coach_name=c2.selectbox("教練",list(allowed),key="event_coach")
            content=st.text_input("活動內容")
            c1,c2=st.columns(2); hours=c1.number_input("時數",0.25,24.0,1.0,step=0.25,key="event_hours"); deducted_hours=c2.number_input("應扣除時間",0.0,24.0,0.0,step=0.25)
            reason=st.text_input("扣除原因"); save=st.form_submit_button("新增紀錄")
        if save:
            if not content.strip(): st.error("活動內容不可空白。")
            elif deducted_hours>hours: st.error("應扣除時間不可大於活動時數。")
            elif deducted_hours>0 and not reason.strip(): st.error("有扣除時間時必須填寫扣除原因。")
            else:
                try:
                    client().table("event_supports").insert({"entry_date":str(entry_date),"content":content.strip(),"hours":hours,"coach_id":allowed[coach_name],"deducted_hours":deducted_hours,"deduction_reason":reason.strip() or None,"created_by":me["id"]}).execute()
                    st.success("紀錄已新增。"); st.rerun()
                except Exception as exc: st.error(f"新增失敗：{exc}")
        data=rows(client().table("event_supports").select("entry_date,content,hours,deducted_hours,deduction_reason,coach_id").order("entry_date",desc=True).limit(100))
        data=[x for x in data if x.get("coach_id") in names]
        for x in data: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
        show_table(data,["entry_date","content","coach_name","hours","deducted_hours","deduction_reason"])

def purchase_page(me):
    st.header("課程購買")
    coaches=coach_options(); allowed=coaches if me["role"] in ("shared_coach","manager","admin") else {me["display_name"]:me["id"]}
    courses=rows(client().table("course_catalog").select("course_name,session_hours").order("course_name"))
    course_names=[x["course_name"] for x in courses]
    course_hours={x["course_name"]:float(x.get("session_hours") or 1) for x in courses}
    if not course_names:
        st.warning("尚未建立課程名稱，請由系統管理員先到「課程名稱管理」新增。")
        return
    plan=st.selectbox("付款方式",["未分期","分期"],key="purchase_payment_plan")
    with st.form("purchase"):
        c1,c2,c3=st.columns(3)
        member_name=c1.text_input("會員名稱（需完整一致）")
        kind=c2.selectbox("購買類型",["首次購買","續課"])
        coach_name=c3.selectbox("指導教練",list(allowed))
        c1,c2,c3,c4=st.columns(4)
        course=c1.selectbox("課程名稱",course_names)
        sessions=c2.number_input("課程堂數",1,999,1)
        session_hours=c3.number_input("每堂課時數",0.25,24.0,course_hours[course],step=0.25,format="%.2f",disabled=True)
        amount=c4.number_input("成交總金額",0.0,10000000.0,step=100.0,format="%.0f")
        c1,c2=st.columns(2)
        purchased=c1.date_input("購買日期",date.today())
        expiry=c2.date_input("有效日期",date.today()+timedelta(days=365))
        if plan=="分期":
            count=st.selectbox("總期數",[2,3])
            c1,c2,c3=st.columns(3)
            installment_no=c1.selectbox("此次為第幾期",list(range(1,count+1)))
            paid=c2.number_input("此次支付金額",0.0,10000000.0,step=100.0,format="%.0f")
            paid_date=c3.date_input("支付日期",purchased)
        else:
            count=1
            installment_no=1
            paid=amount
            paid_date=purchased
            st.caption("未分期將於建立紀錄時，自動以成交總金額記錄為一次付清。")
        save=st.form_submit_button("建立購買紀錄")
    if save:
        errors=[]
        if not member_name.strip(): errors.append("會員名稱不可空白")
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
                    "coach_id":allowed[coach_name],"course_name":course.strip(),"total_sessions":sessions,"session_hours":session_hours,"total_amount":amount,
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
            no=c1.selectbox("期次",[1,2,3]); pay_amount=c2.number_input("支付金額",1.0,10000000.0,step=100.0,format="%.0f"); pay_date=c3.date_input("付款日期",date.today())
            add=st.form_submit_button("新增付款")
        if add:
            try:
                client().table("purchase_payments").insert({"purchase_id":lookup[label],"installment_no":no,"amount":pay_amount,"paid_date":str(pay_date),"created_by":me["id"]}).execute()
                st.success("付款紀錄已新增。")
            except Exception as exc: st.error(f"新增失敗（請檢查期次是否重複或超出設定）：{exc}")

def usage_query_tabs():
    st.divider()
    st.subheader("銷課查詢")
    coaches=coach_options()
    operational_ids=set(coaches.values())
    balances=rows(client().table("purchase_balances").select("*").order("expiry_date"))
    balances=[x for x in balances if x.get("coach_id") in operational_ids]
    purchase_ids=[x["purchase_id"] for x in balances]
    purchases=[]
    payments=[]
    if purchase_ids:
        purchases=rows(client().table("purchases").select("id,payment_plan,installment_count,session_hours").in_("id",purchase_ids))
        payments=rows(client().table("purchase_payments").select("purchase_id,installment_no,amount").in_("purchase_id",purchase_ids))
    purchase_map={x["id"]:x for x in purchases}
    payment_map={}
    for payment in payments:
        summary=payment_map.setdefault(payment["purchase_id"],{"amount":0.0,"count":0})
        summary["amount"]+=float(payment["amount"])
        summary["count"]+=1

    tab1,tab2,tab3=st.tabs(["會員課程查詢","銷課統計","一個月內到期"])
    with tab1:
        selected_coach=st.selectbox("成交教練",["全部教練"]+list(coaches),key="member_course_coach_filter")
        filtered_balances=balances if selected_coach=="全部教練" else [
            x for x in balances if x.get("coach_id")==coaches[selected_coach]
        ]
        detail=[]
        for item in filtered_balances:
            purchase=purchase_map.get(item["purchase_id"],{})
            payment=payment_map.get(item["purchase_id"],{"amount":0.0,"count":0})
            total_amount=float(item["total_amount"])
            if payment["amount"] >= total_amount:
                payment_status="已付清"
            elif purchase.get("payment_plan")=="installment":
                payment_status=f'已付 {payment["count"]}/{purchase.get("installment_count", "-")} 期，TWD {payment["amount"]:,.0f}'
            else:
                payment_status=f'尚欠 TWD {total_amount-payment["amount"]:,.0f}'
            detail.append({
                "會員名稱":item["member_name"],"課程名稱":item["course_name"],"成交教練":item["coach_name"],
                "購買堂數":item["total_sessions"],"每堂課時數":float(purchase.get("session_hours") or 1),"成交金額":total_amount,"已上堂數":item["used_sessions"],
                "剩餘堂數":item["remaining_sessions"],"剩餘金額":float(item["remaining_amount"]),
                "有效期限":item["expiry_date"],"分期支付狀況":payment_status,
            })
        if detail:
            st.dataframe(pd.DataFrame(detail),hide_index=True,use_container_width=True,
                column_config={"成交金額":st.column_config.NumberColumn(format="TWD %.0f"),
                               "剩餘金額":st.column_config.NumberColumn(format="TWD %.0f")})
        else:
            st.info("目前沒有可查詢的課程資料。")

    with tab2:
        c1,c2=st.columns(2)
        query_start=c1.date_input("開始日期",date.today().replace(day=1),key="usage_query_start")
        query_end=c2.date_input("結束日期",date.today(),key="usage_query_end")
        if query_start>query_end:
            st.error("開始日期不可晚於結束日期。")
        else:
            usages=rows(client().table("session_usages").select("usage_date,coach_id,deducted_amount").gte("usage_date",str(query_start)).lte("usage_date",str(query_end)))
            usages=[x for x in usages if x.get("coach_id") in operational_ids]
            total_sessions=len(usages)
            total_amount=sum(float(x["deducted_amount"]) for x in usages)
            average=total_amount/total_sessions if total_sessions else 0
            a,b,c=st.columns(3)
            a.metric("總銷課堂數",f"{total_sessions:,}")
            b.metric("總銷課金額",f"TWD {total_amount:,.0f}")
            c.metric("平均單價",f"TWD {average:,.0f}")
            by_coach=[]
            for coach_name,coach_id in coaches.items():
                coach_rows=[x for x in usages if x["coach_id"]==coach_id]
                if coach_rows:
                    coach_amount=sum(float(x["deducted_amount"]) for x in coach_rows)
                    by_coach.append({"教練":coach_name,"銷課堂數":len(coach_rows),"銷課金額":coach_amount,
                                     "平均單價":coach_amount/len(coach_rows)})
            if by_coach:
                st.dataframe(pd.DataFrame(by_coach),hide_index=True,use_container_width=True,
                    column_config={"銷課金額":st.column_config.NumberColumn(format="TWD %.0f"),
                                   "平均單價":st.column_config.NumberColumn(format="TWD %.0f")})

    with tab3:
        today=date.today()
        deadline=today+timedelta(days=30)
        expiring=[x for x in balances if x["status"]=="active" and x["remaining_sessions"]>0
                  and today<=pd.to_datetime(x["expiry_date"]).date()<=deadline]
        st.caption(f"查詢期間：{today} 至 {deadline}")
        if expiring:
            expiry_rows=[{"會員名稱":x["member_name"],"課程名稱":x["course_name"],"成交教練":x["coach_name"],
                          "剩餘堂數":x["remaining_sessions"],"剩餘金額":float(x["remaining_amount"]),
                          "有效期限":x["expiry_date"],"剩餘天數":(pd.to_datetime(x["expiry_date"]).date()-today).days}
                         for x in expiring]
            st.dataframe(pd.DataFrame(expiry_rows),hide_index=True,use_container_width=True,
                column_config={"剩餘金額":st.column_config.NumberColumn(format="TWD %.0f")})
        else:
            st.info("未來 30 天內沒有即將到期且仍有剩餘堂數的課程。")

def usage_page(me):
    st.header("銷課表")
    coaches=coach_options(); allowed=coaches if me["role"] in ("shared_coach","manager","admin") else {me["display_name"]:me["id"]}
    with st.expander("新增銷課取消紀錄",expanded=False):
        with st.form("session_cancellation",clear_on_submit=True):
            c1,c2,c3=st.columns(3); cancel_date=c1.date_input("取消日期",date.today()); cancel_coach=c2.selectbox("教練",list(allowed)); cancel_count=c3.number_input("銷課取消堂數",0,100,0)
            cancel_reason=st.text_input("取消原因"); add_cancel=st.form_submit_button("新增取消紀錄")
        if add_cancel:
            try:
                client().table("session_cancellations").insert({"cancel_date":str(cancel_date),"coach_id":allowed[cancel_coach],"cancelled_sessions":cancel_count,"reason":cancel_reason.strip() or None,"created_by":me["id"]}).execute()
                st.success("銷課取消紀錄已新增。"); st.rerun()
            except Exception as exc: st.error(f"新增失敗：{exc}")
        cancellations=rows(client().table("session_cancellations").select("cancel_date,coach_id,cancelled_sessions,reason").order("cancel_date",desc=True).limit(100))
        coach_names={v:k for k,v in coaches.items()}; cancellations=[x for x in cancellations if x.get("coach_id") in coach_names]
        for x in cancellations: x["coach_name"]=coach_names.get(x.pop("coach_id"),"未知")
        show_table(cancellations,["cancel_date","coach_name","cancelled_sessions","reason"])
    members=rows(client().table("members").select("id,member_name").eq("active",True).order("member_name"))
    if not members: st.info("請先建立課程購買紀錄。") ; usage_query_tabs() ; return
    member_map={x["member_name"]:x["id"] for x in members}
    member_name=st.selectbox("會員名稱",list(member_map),index=None,placeholder="輸入或選擇會員")
    if not member_name: usage_query_tabs() ; return
    balances=rows(client().table("purchase_balances").select("*").eq("member_id",member_map[member_name]).gt("remaining_sessions",0).order("expiry_date"))
    balances=[x for x in balances if x.get("coach_id") in set(coaches.values())]
    show_table(balances,["course_name","coach_name","total_sessions","used_sessions","remaining_sessions","remaining_amount","expiry_date","status"])
    active=[x for x in balances if x["status"]=="active"]
    if not active: st.warning("此會員沒有可扣課的有效課程。") ; usage_query_tabs() ; return
    lookup={f'{x["course_name"]}｜成交教練：{x["coach_name"]}｜剩 {x["remaining_sessions"]} 堂｜餘額 {x["remaining_amount"]}':x for x in active}
    with st.form("consume"):
        label=st.selectbox("選擇課程",list(lookup)); selected=lookup[label]
        st.info(f'成交教練：{selected["coach_name"]}')
        c1,c2=st.columns(2); usage_date=c1.date_input("銷課日期",date.today()); coach=c2.selectbox("授課教練",list(allowed))
        note=st.text_input("備註"); submit=st.form_submit_button("確認扣除 1 堂")
    per=Decimal(str(selected["remaining_amount"])) if selected["remaining_sessions"]==1 else (Decimal(str(selected["total_amount"]))/selected["total_sessions"]).quantize(Decimal("0.01"))
    st.caption(f"本次預計扣除：1 堂／TWD {per:,.0f}；最後一堂會自動扣完剩餘金額。")
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
    usage_query_tabs()

def dashboard_page(me):
    st.header("主管 Dashboard")
    if me["role"] not in ("manager","admin"): st.warning("此頁僅限主管與系統管理員使用。") ; return
    coaches=coach_options(); c1,c2,c3=st.columns(3)
    start=c1.date_input("開始日期",date.today().replace(day=1)); end=c2.date_input("結束日期",date.today())
    selected=c3.multiselect("教練",list(coaches),default=list(coaches))
    if start>end: st.error("開始日期不可晚於結束日期。") ; return
    ids=[coaches[x] for x in selected]
    cancellations=rows(client().table("session_cancellations").select("coach_id,cancelled_sessions,cancel_date").gte("cancel_date",str(start)).lte("cancel_date",str(end)))
    trials=rows(client().table("trial_items").select("coach_id,member_name,entry_date").gte("entry_date",str(start)).lte("entry_date",str(end)))
    purchases=rows(client().table("purchases").select("id,coach_id,purchase_kind,total_sessions,total_amount,purchase_date").gte("purchase_date",str(start)).lte("purchase_date",str(end)))
    usages=rows(client().table("session_usages").select("coach_id,deducted_amount,usage_date").gte("usage_date",str(start)).lte("usage_date",str(end)))
    payments=rows(client().table("purchase_payments").select("purchase_id,amount,paid_date").gte("paid_date",str(start)).lte("paid_date",str(end)))
    payment_purchase_ids=list({x["purchase_id"] for x in payments})
    payment_purchase_map={}
    if payment_purchase_ids:
        payment_purchases=rows(client().table("purchases").select("id,coach_id").in_("id",payment_purchase_ids))
        payment_purchase_map={x["id"]:x["coach_id"] for x in payment_purchases}
    names={v:k for k,v in coaches.items()}; result=[]
    for cid in ids:
        p=[x for x in purchases if x["coach_id"]==cid]
        u=[x for x in usages if x["coach_id"]==cid]
        cancelled=sum(x["cancelled_sessions"] for x in cancellations if x["coach_id"]==cid)
        sessions=sum(x["total_sessions"] for x in p); amount=sum(float(x["total_amount"]) for x in p)
        trial_names={str(x.get("member_name") or "").strip().casefold() for x in trials if x["coach_id"]==cid and str(x.get("member_name") or "").strip()}
        trial_count=len(trial_names)
        first_count=sum(1 for x in p if x["purchase_kind"]=="first")
        renewal_count=sum(1 for x in p if x["purchase_kind"]=="renewal")
        received=sum(float(x["amount"]) for x in payments if payment_purchase_map.get(x["purchase_id"])==cid)
        used_sessions=len(u); used_amount=sum(float(x["deducted_amount"]) for x in u)
        result.append({"教練":names[cid],"銷課堂數":used_sessions,"銷課金額":used_amount,
                       "銷課取消率":cancelled/(used_sessions+cancelled) if used_sessions+cancelled else None,
                       "體驗人次":trial_count,"體驗成交率":first_count/trial_count if trial_count else None,
                       "續約率":renewal_count/len(p) if p else None,"成交堂數":sessions,
                       "成交總金額":amount,"實際預收金額":received,
                       "平均每堂單價":amount/sessions if sessions else None})
    df=pd.DataFrame(result)
    if df.empty: st.info("沒有可顯示的資料。") ; return
    totals=df[["成交堂數","成交總金額","實際預收金額","銷課堂數","銷課金額"]].sum()
    overall_trial_names={str(x.get("member_name") or "").strip().casefold() for x in trials if x["coach_id"] in ids and str(x.get("member_name") or "").strip()}
    total_trial_count=len(overall_trial_names)
    total_first_count=len([x for x in purchases if x["coach_id"] in ids and x["purchase_kind"]=="first"])
    overall_trial_conversion=total_first_count/total_trial_count if total_trial_count else None
    total_purchase_count=len([x for x in purchases if x["coach_id"] in ids])
    total_renewals=len([x for x in purchases if x["coach_id"] in ids and x["purchase_kind"]=="renewal"])
    overall_renewal=total_renewals/total_purchase_count if total_purchase_count else None
    total_cancelled=sum(x["cancelled_sessions"] for x in cancellations if x["coach_id"] in ids)
    overall_cancel_rate=total_cancelled/(totals["銷課堂數"]+total_cancelled) if totals["銷課堂數"]+total_cancelled else None
    average_unit=totals["成交總金額"]/totals["成交堂數"] if totals["成交堂數"] else None
    a,b,c,d,e,f=st.columns(6)
    a.metric("銷課堂數",f'{totals["銷課堂數"]:,.0f}')
    b.metric("銷課金額",f'TWD {totals["銷課金額"]:,.0f}')
    c.metric("銷課取消率",f'{overall_cancel_rate:.1%}' if overall_cancel_rate is not None else "—")
    d.metric("體驗人次",f'{total_trial_count:,.0f}')
    e.metric("體驗成交率",f'{overall_trial_conversion:.1%}' if overall_trial_conversion is not None else "—")
    f.metric("續約率",f'{overall_renewal:.1%}' if overall_renewal is not None else "—")
    a2,b2,c2,d2=st.columns(4)
    a2.metric("成交堂數",f'{totals["成交堂數"]:,.0f}')
    b2.metric("成交總金額",f'TWD {totals["成交總金額"]:,.0f}')
    c2.metric("實際預收金額",f'TWD {totals["實際預收金額"]:,.0f}')
    d2.metric("平均每堂單價",f'TWD {average_unit:,.0f}' if average_unit is not None else "—")
    display_df=df.copy()
    display_df["銷課取消率"]=display_df["銷課取消率"]*100
    display_df["體驗成交率"]=display_df["體驗成交率"]*100
    display_df["續約率"]=display_df["續約率"]*100
    display_df=display_df[["教練","銷課堂數","銷課金額","銷課取消率","體驗人次","體驗成交率","續約率","成交堂數","成交總金額","實際預收金額","平均每堂單價"]]
    st.dataframe(display_df,hide_index=True,use_container_width=True,column_config={"銷課取消率":st.column_config.NumberColumn(format="%.1f%%"),"體驗成交率":st.column_config.NumberColumn(format="%.1f%%"),"續約率":st.column_config.NumberColumn(format="%.1f%%"),"成交總金額":st.column_config.NumberColumn(format="TWD %.0f"),"實際預收金額":st.column_config.NumberColumn(format="TWD %.0f"),"銷課金額":st.column_config.NumberColumn(format="TWD %.0f"),"平均每堂單價":st.column_config.NumberColumn(format="TWD %.0f")})
    left,right=st.columns(2)
    count_metric=left.selectbox("數量指標",["成交堂數","銷課堂數","體驗人次"],key="dashboard_count_metric")
    amount_metric=right.selectbox("金額類型",["成交總金額","銷課金額"],key="dashboard_amount_metric")
    count_unit="人次" if count_metric=="體驗人次" else "堂數"
    left.plotly_chart(px.bar(df,x="教練",y=count_metric,title=f"{count_metric}比較（{start} 至 {end}）",labels={count_metric:count_unit}),use_container_width=True)
    right.plotly_chart(px.bar(df,x="教練",y=amount_metric,title=f"{amount_metric}比較（{start} 至 {end}）",labels={amount_metric:"TWD"}),use_container_width=True)

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
        role_label = c2.selectbox("權限", ["教練", "共用教練帳號", "主管", "系統管理員"])
        create_account = st.form_submit_button("建立帳號")
    if create_account:
        role_value = {"教練":"coach", "共用教練帳號":"shared_coach", "主管":"manager", "系統管理員":"admin"}[role_label]
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
            new_role_label = st.selectbox("權限", ["教練", "共用教練帳號", "主管", "系統管理員"])
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
                    role_value={"教練":"coach","共用教練帳號":"shared_coach","主管":"manager","系統管理員":"admin"}[new_role_label]
                    admin.table("profiles").update({"role":role_value,"active":new_active=="啟用"}).eq("id",target["id"]).execute()
                    if reset_password: admin.auth.admin.update_user_by_id(target["id"], {"password":reset_password})
                    st.success("帳號與權限已更新。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"更新失敗：{exc}")

        st.subheader("刪除帳號")
        deletable = {label: item for label, item in labels.items() if item["id"] != me["id"]}
        if deletable:
            with st.form("delete_account"):
                delete_label = st.selectbox("選擇要刪除的帳號", list(deletable))
                confirm_account_delete = st.checkbox("我確認永久刪除此帳號。此操作無法復原。")
                delete_account = st.form_submit_button("永久刪除帳號")
            if delete_account:
                if not confirm_account_delete:
                    st.error("請先勾選刪除確認。")
                else:
                    target = deletable[delete_label]
                    references = 0
                    for table_name, field in (("daily_operations","coach_id"),("purchases","coach_id"),
                                              ("session_usages","coach_id"),("members","created_by"),
                                              ("purchase_payments","created_by")):
                        references += len(rows(admin.table(table_name).select("id").eq(field,target["id"]).limit(1)))
                    if references:
                        st.error("此帳號已有營運資料，為保留歷史紀錄不可永久刪除；請改為『停用』。")
                    else:
                        try:
                            admin.auth.admin.delete_user(target["id"])
                            st.success(f"已永久刪除帳號：{target.get('username') or target['display_name']}")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"刪除失敗：{exc}")

def course_admin_page(me):
    st.header("課程名稱管理")
    if me["role"] != "admin":
        st.warning("此頁僅限系統管理員使用。")
        return
    admin=admin_client()
    if admin is None:
        st.error("尚未設定 SUPABASE_SECRET_KEY。")
        return
    with st.form("add_course",clear_on_submit=True):
        c1,c2=st.columns(2)
        course_name=c1.text_input("新增課程名稱").strip()
        course_hours=c2.number_input("每堂課時數",0.25,24.0,1.0,step=0.25,format="%.2f")
        add_course=st.form_submit_button("新增課程")
    if add_course:
        if not course_name:
            st.error("課程名稱不可空白。")
        else:
            try:
                admin.table("course_catalog").insert({"course_name":course_name,"session_hours":course_hours}).execute()
                st.success(f"已新增課程：{course_name}")
                st.rerun()
            except Exception as exc:
                st.error(f"新增失敗，請確認課程名稱是否重複：{exc}")
    courses=rows(admin.table("course_catalog").select("id,course_name,session_hours,created_at").order("course_name"))
    if not courses:
        st.info("目前尚未建立課程名稱。")
        return
    show_table(courses,["course_name","session_hours","created_at"])
    course_labels={x["course_name"]:x["id"] for x in courses}
    with st.form("delete_course"):
        selected_course=st.selectbox("選擇要刪除的課程",list(course_labels))
        confirm_delete=st.checkbox("我確認刪除此課程名稱；既有會員購買紀錄仍會保留。")
        delete_course=st.form_submit_button("刪除課程名稱")
    if delete_course:
        if not confirm_delete:
            st.error("請先勾選刪除確認。")
        else:
            try:
                admin.table("course_catalog").delete().eq("id",course_labels[selected_course]).execute()
                st.success(f"已刪除課程名稱：{selected_course}")
                st.rerun()
            except Exception as exc:
                st.error(f"刪除失敗：{exc}")

def operation_item_admin_page(me, item_type, title):
    st.subheader(title)
    if me["role"] != "admin":
        st.warning("此功能僅限系統管理員使用。")
        return
    admin=admin_client()
    if admin is None:
        st.error("尚未設定 SUPABASE_SECRET_KEY。")
        return
    with st.form(f"add_operation_item_{item_type}",clear_on_submit=True):
        new_name=st.text_input("新增項目名稱").strip()
        add_item=st.form_submit_button("新增項目")
    if add_item:
        if not new_name:
            st.error("項目名稱不可空白。")
        else:
            try:
                admin.table("operation_item_catalog").insert({"item_type":item_type,"item_name":new_name}).execute()
                st.success(f"已新增：{new_name}"); st.rerun()
            except Exception as exc:
                st.error(f"新增失敗，請確認名稱是否重複：{exc}")
    items=rows(admin.table("operation_item_catalog").select("id,item_name,created_at").eq("item_type",item_type).order("item_name"))
    if not items:
        st.info("目前尚未建立項目。")
        return
    show_table(items,["item_name","created_at"])
    item_map={x["item_name"]:x["id"] for x in items}
    with st.form(f"edit_operation_item_{item_type}"):
        selected=st.selectbox("選擇項目",list(item_map))
        edited_name=st.text_input("修改後名稱",value=selected).strip()
        update_item=st.form_submit_button("儲存修改")
    if update_item:
        if not edited_name:
            st.error("項目名稱不可空白。")
        else:
            try:
                admin.table("operation_item_catalog").update({"item_name":edited_name}).eq("id",item_map[selected]).execute()
                st.success("項目已修改。既有歷史紀錄仍保留原內容。")
                st.rerun()
            except Exception as exc:
                st.error(f"修改失敗，請確認名稱是否重複：{exc}")
    with st.form(f"delete_operation_item_{item_type}"):
        delete_name=st.selectbox("選擇要刪除的項目",list(item_map),key=f"delete_select_{item_type}")
        confirm=st.checkbox("我確認刪除此下拉選項；既有歷史紀錄不會被刪除。")
        delete_item=st.form_submit_button("刪除項目")
    if delete_item:
        if not confirm:
            st.error("請先勾選確認。")
        else:
            try:
                admin.table("operation_item_catalog").delete().eq("id",item_map[delete_name]).execute()
                st.success(f"已刪除選項：{delete_name}"); st.rerun()
            except Exception as exc:
                st.error(f"刪除失敗：{exc}")

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

def member_course_io_page(me):
    admin=admin_client()
    profiles=rows(admin.table("profiles").select("id,username,display_name,role"))
    coach_profiles=[x for x in profiles if x["role"] in ("coach","manager")]
    id_to_username={x["id"]:x.get("username") or x["display_name"] for x in coach_profiles}
    username_to_id={v:k for k,v in id_to_username.items()}
    members=rows(admin.table("members").select("id,member_name"))
    member_names={x["id"]:x["member_name"] for x in members}

    st.subheader("匯出會員課程與銷課表")
    purchases=rows(admin.table("purchases").select("*").order("purchase_date"))
    payments=rows(admin.table("purchase_payments").select("purchase_id,amount,paid_date"))
    paid_map={}
    paid_date_map={}
    for x in payments:
        paid_map[x["purchase_id"]]=paid_map.get(x["purchase_id"],0)+float(x["amount"])
        paid_date_map[x["purchase_id"]]=max(str(x["paid_date"]),paid_date_map.get(x["purchase_id"],""))
    course_rows=[]
    for x in purchases:
        course_rows.append({"purchase_id":x["id"],"member_name":member_names.get(x["member_id"],""),
            "purchase_kind":x["purchase_kind"],"coach_username":id_to_username.get(x["coach_id"],""),
            "course_name":x["course_name"],"total_sessions":x["total_sessions"],"session_hours":x.get("session_hours",1),
            "total_amount":x["total_amount"],"purchase_date":x["purchase_date"],"expiry_date":x["expiry_date"],
            "payment_plan":x["payment_plan"],"installment_count":x["installment_count"],
            "paid_amount":paid_map.get(x["id"],0),"paid_date":paid_date_map.get(x["id"],"")})
    usages=rows(admin.table("session_usages").select("*").order("usage_date"))
    purchase_map={x["id"]:x for x in purchases}
    usage_rows=[]
    for x in usages:
        p=purchase_map.get(x["purchase_id"],{})
        usage_rows.append({"usage_id":x["id"],"purchase_id":x["purchase_id"],
            "member_name":member_names.get(p.get("member_id"),""),"course_name":p.get("course_name",""),
            "usage_date":x["usage_date"],"coach_username":id_to_username.get(x["coach_id"],""),
            "session_seq":x["session_seq"],"deducted_amount":x["deducted_amount"],"note":x.get("note") or ""})
    report=_excel_bytes({"會員課程":pd.DataFrame(course_rows),"銷課表":pd.DataFrame(usage_rows)})
    st.download_button("下載會員課程與銷課表",report,file_name=f"會員課程與銷課表_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

    st.divider(); st.subheader("匯入會員課程與銷課表")
    st.caption("請先下載範本。匯入會員課程時 purchase_id 可留空；匯入銷課表時 purchase_id 必須對應系統內的購買紀錄。")
    course_template=pd.DataFrame(columns=["purchase_id","member_name","purchase_kind","coach_username","course_name","total_sessions","session_hours","total_amount","purchase_date","expiry_date","payment_plan","installment_count","paid_amount","paid_date"])
    usage_template=pd.DataFrame(columns=["purchase_id","usage_date","coach_username","note"])
    st.download_button("下載匯入範本",_excel_bytes({"會員課程":course_template,"銷課表":usage_template}),
        file_name="會員課程與銷課表_匯入範本.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    uploaded=st.file_uploader("選擇 Excel 檔案",type=["xlsx"],key="course_usage_import")
    if uploaded is not None:
        try:
            book=pd.ExcelFile(uploaded); errors=[]; clean_courses=[]; clean_usages=[]
            if not any(x in book.sheet_names for x in ("會員課程","銷課表")):
                errors.append("至少需要『會員課程』或『銷課表』工作表。")
            if "會員課程" in book.sheet_names:
                df=pd.read_excel(book,"會員課程").fillna("")
                required=set(course_template.columns)-{"purchase_id"}
                if not required.issubset(df.columns): errors.append("會員課程欄位不完整。")
                else:
                    for i,row in df.iterrows():
                        try:
                            username=str(row["coach_username"]).strip()
                            if username not in username_to_id: raise ValueError("找不到教練帳號")
                            kind=str(row["purchase_kind"]).strip().lower(); plan=str(row["payment_plan"]).strip().lower()
                            if kind not in ("first","renewal"): raise ValueError("purchase_kind 必須為 first 或 renewal")
                            if plan not in ("full","installment"): raise ValueError("payment_plan 必須為 full 或 installment")
                            purchased=pd.to_datetime(row["purchase_date"]).date(); expiry=pd.to_datetime(row["expiry_date"]).date()
                            if expiry<purchased: raise ValueError("有效日期不可早於購買日期")
                            clean_courses.append({"source_id":str(row.get("purchase_id","")).strip(),"member_name":str(row["member_name"]).strip(),
                                "coach_id":username_to_id[username],"purchase_kind":kind,"course_name":str(row["course_name"]).strip(),
                                "total_sessions":int(row["total_sessions"]),"session_hours":float(row["session_hours"]),"total_amount":float(row["total_amount"]),
                                "purchase_date":str(purchased),"expiry_date":str(expiry),"payment_plan":plan,"installment_count":int(row["installment_count"]),
                                "paid_amount":float(row["paid_amount"] or 0),"paid_date":str(pd.to_datetime(row["paid_date"]).date()) if row["paid_date"] else str(purchased)})
                        except Exception as exc: errors.append(f"會員課程第 {i+2} 列：{exc}")
            if "銷課表" in book.sheet_names:
                df=pd.read_excel(book,"銷課表").fillna("")
                if not set(usage_template.columns).issubset(df.columns): errors.append("銷課表欄位不完整。")
                else:
                    for i,row in df.iterrows():
                        try:
                            username=str(row["coach_username"]).strip()
                            if username not in username_to_id: raise ValueError("找不到教練帳號")
                            clean_usages.append({"purchase_id":str(row["purchase_id"]).strip(),"usage_date":str(pd.to_datetime(row["usage_date"]).date()),"coach_id":username_to_id[username],"note":str(row["note"]).strip() or None})
                        except Exception as exc: errors.append(f"銷課表第 {i+2} 列：{exc}")
            if errors: st.error("匯入檢查未通過：\n- "+"\n- ".join(errors[:30]))
            else:
                st.success(f"檢查通過：會員課程 {len(clean_courses)} 筆、銷課 {len(clean_usages)} 筆。")
                if st.button("確認匯入",type="primary"):
                    for item in clean_courses:
                        existing=rows(admin.table("members").select("id").eq("member_name",item["member_name"]))
                        member_id=existing[0]["id"] if existing else rows(admin.table("members").insert({"member_name":item["member_name"],"created_by":me["id"]}))[0]["id"]
                        payload={k:v for k,v in item.items() if k not in ("source_id","member_name","paid_amount","paid_date")}
                        payload.update({"member_id":member_id,"created_by":me["id"]})
                        created=rows(admin.table("purchases").insert(payload))[0]
                        if item["paid_amount"]>0: admin.table("purchase_payments").insert({"purchase_id":created["id"],"installment_no":1,"amount":item["paid_amount"],"paid_date":item["paid_date"],"created_by":me["id"]}).execute()
                    valid_ids={x["id"] for x in rows(admin.table("purchases").select("id"))}
                    for item in clean_usages:
                        if item["purchase_id"] not in valid_ids: raise ValueError(f'找不到 purchase_id：{item["purchase_id"]}')
                        client().rpc("consume_session",{"p_purchase_id":item["purchase_id"],"p_usage_date":item["usage_date"],"p_coach_id":item["coach_id"],"p_note":item["note"]}).execute()
                    st.success("資料匯入完成。")
        except Exception as exc: st.error(f"無法匯入檔案：{exc}")

def _sync_daily_classes(admin, operation_date, coach_id):
    held=len(rows(admin.table("session_usages").select("id").eq("usage_date",str(operation_date)).eq("coach_id",coach_id)))
    existing=rows(admin.table("daily_operations").select("id").eq("operation_date",str(operation_date)).eq("coach_id",coach_id))
    if existing:
        admin.table("daily_operations").update({"classes_held":held}).eq("id",existing[0]["id"]).execute()
    elif held:
        admin.table("daily_operations").insert({"operation_date":str(operation_date),"coach_id":coach_id,"classes_held":held,"classes_cancelled":0,"trial_visits":0,"trial_conversions":0}).execute()

def record_admin_page(me):
    admin=admin_client(); coaches=rows(admin.table("profiles").select("id,display_name,role"))
    coach_map={x["display_name"]:x["id"] for x in coaches if x["role"] in ("coach","manager")}; id_name={v:k for k,v in coach_map.items()}
    data_type=st.selectbox("資料類型",["每日營運","課程購買","銷課表"],key="manage_data_type")
    if data_type=="每日營運":
        records=rows(admin.table("daily_operations").select("*").order("operation_date",desc=True).limit(500))
        labels={f'{x["operation_date"]}｜{id_name.get(x["coach_id"],"未知")}｜{x["id"][:8]}':x for x in records}
    elif data_type=="課程購買":
        records=rows(admin.table("purchase_balances").select("*").order("expiry_date",desc=True).limit(500))
        labels={f'{x["member_name"]}｜{x["course_name"]}｜{x["purchase_id"][:8]}':x for x in records}
    else:
        records=rows(admin.table("session_usages").select("*").order("usage_date",desc=True).limit(500))
        labels={f'{x["usage_date"]}｜{id_name.get(x["coach_id"],"未知")}｜第{x["session_seq"]}堂｜{x["id"][:8]}':x for x in records}
    if not labels: st.info("目前沒有可管理的資料。"); return
    selected=st.selectbox("選擇紀錄",list(labels)); record=labels[selected]
    record_coach_map=dict(coach_map)
    if data_type in ("每日營運","銷課表") and record.get("coach_id") not in record_coach_map.values():
        historical_name=id_name.get(record.get("coach_id"),f'歷史帳號 {str(record.get("coach_id",""))[:8]}')
        record_coach_map[f'{historical_name}（歷史資料）']=record.get("coach_id")
    coach_names=list(record_coach_map)
    current_coach_index=list(record_coach_map.values()).index(record.get("coach_id")) if record.get("coach_id") in record_coach_map.values() else 0
    with st.form("record_edit"):
        if data_type=="每日營運":
            c1,c2=st.columns(2); d=c1.date_input("日期",pd.to_datetime(record["operation_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index)
            c1,c2,c3=st.columns(3); cancelled=c1.number_input("取消堂數",0,999,int(record["classes_cancelled"])); trials=c2.number_input("體驗人次",0,999,int(record["trial_visits"])); conversions=c3.number_input("體驗成交人次",0,999,int(record["trial_conversions"])); note=st.text_area("備註",record.get("note") or "")
        elif data_type=="課程購買":
            c1,c2,c3=st.columns(3); sessions=c1.number_input("課程堂數",1,999,int(record["total_sessions"])); amount=c2.number_input("成交總金額",0.0,10000000.0,float(record["total_amount"]),step=100.0,format="%.0f"); expiry=c3.date_input("有效期限",pd.to_datetime(record["expiry_date"]).date())
        else:
            c1,c2=st.columns(2); d=c1.date_input("銷課日期",pd.to_datetime(record["usage_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index); note=st.text_area("備註",record.get("note") or "")
        update=st.form_submit_button("儲存修改")
    if update:
        try:
            if data_type=="每日營運":
                if conversions>trials: raise ValueError("體驗成交人次不可大於體驗人次")
                held=len(rows(admin.table("session_usages").select("id").eq("usage_date",str(d)).eq("coach_id",record_coach_map[coach])))
                admin.table("daily_operations").update({"operation_date":str(d),"coach_id":record_coach_map[coach],"classes_held":held,"classes_cancelled":cancelled,"trial_visits":trials,"trial_conversions":conversions,"note":note or None}).eq("id",record["id"]).execute()
            elif data_type=="課程購買": admin.table("purchases").update({"total_sessions":sessions,"total_amount":amount,"expiry_date":str(expiry)}).eq("id",record["purchase_id"]).execute()
            else:
                old_date,old_coach=record["usage_date"],record["coach_id"]
                admin.table("session_usages").update({"usage_date":str(d),"coach_id":record_coach_map[coach],"note":note or None}).eq("id",record["id"]).execute()
                _sync_daily_classes(admin,old_date,old_coach); _sync_daily_classes(admin,d,record_coach_map[coach])
            st.success("資料已修改。"); st.rerun()
        except Exception as exc: st.error(f"修改失敗：{exc}")
    with st.form("record_delete"):
        confirm=st.checkbox("我確認刪除此筆資料；此操作無法復原。")
        delete=st.form_submit_button("刪除紀錄")
    if delete:
        if not confirm: st.error("請先勾選刪除確認。")
        else:
            try:
                if data_type=="每日營運": admin.table("daily_operations").delete().eq("id",record["id"]).execute()
                elif data_type=="課程購買":
                    affected=rows(admin.table("session_usages").select("usage_date,coach_id").eq("purchase_id",record["purchase_id"]))
                    admin.table("session_usages").delete().eq("purchase_id",record["purchase_id"]).execute(); admin.table("purchases").delete().eq("id",record["purchase_id"]).execute()
                    for item in affected: _sync_daily_classes(admin,item["usage_date"],item["coach_id"])
                else:
                    admin.table("session_usages").delete().eq("id",record["id"]).execute()
                    _sync_daily_classes(admin,record["usage_date"],record["coach_id"])
                st.success("資料已刪除。"); st.rerun()
            except Exception as exc: st.error(f"刪除失敗：{exc}")

def data_management_page(me):
    st.header("資料管理")
    if me["role"]!="admin": st.warning("此頁僅限系統管理員使用。"); return
    if admin_client() is None: st.error("尚未設定 SUPABASE_SECRET_KEY。"); return
    tab1,tab2,tab3,tab4,tab5=st.tabs(["課程名稱管理","體驗項目管理","單堂銷售管理","資料匯入／匯出","查詢／修改／刪除"])
    with tab1: course_admin_page(me)
    with tab2: operation_item_admin_page(me,"trial","體驗項目管理")
    with tab3: operation_item_admin_page(me,"single_sale","單堂銷售管理")
    with tab4: member_course_io_page(me)
    with tab5: record_admin_page(me)

user=login(); me=profile(user.id)
with st.sidebar:
    st.title("🏋️ 營運管理")
    st.write(f'{me["display_name"]}｜{ROLE_LABELS.get(me["role"],me["role"])}')
    pages=["每日營運","課程購買","銷課表"]
    if me["role"] in ("manager","admin"): pages.append("主管 Dashboard")
    if me["role"] == "admin":
        pages.extend(["帳號與權限管理", "資料管理"])
    page=st.radio("功能",pages)
    if st.button("登出"):
        client().auth.sign_out(); st.session_state.clear(); st.rerun()

collapse_sidebar_on_mobile()

try:
    {"每日營運":daily_page,"課程購買":purchase_page,"銷課表":usage_page,"主管 Dashboard":dashboard_page,"帳號與權限管理":account_admin_page,"資料管理":data_management_page}[page](me)
except Exception as exc:
    st.error(f"讀取資料時發生錯誤：{exc}")
