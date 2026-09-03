import os
import re
from io import BytesIO
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from supabase import create_client
from supabase.lib.client_options import ClientOptions

load_dotenv()
st.set_page_config(page_title="秀傳運醫營運系統", page_icon="🏋️", layout="wide")

LABELS = {
    "operation_date":"日期", "coach_name":"教練", "classes_held":"上課堂數",
    "classes_cancelled":"上課取消堂數", "trial_visits":"體驗人次",
    "trial_conversions":"體驗成交人次", "member_name":"會員名稱",
    "trial_member_name":"體驗會員姓名", "single_sale_member_name":"單堂銷售會員姓名",
    "course_name":"課程名稱", "total_sessions":"原始堂數", "session_hours":"每堂課時數",
    "remaining_sessions":"剩餘堂數", "remaining_amount":"剩餘金額",
    "purchase_date":"成交日期", "usage_date":"銷課日期", "session_seq":"第幾堂", "deducted_amount":"扣課金額",
    "entry_date":"日期", "content":"內容", "hours":"時數",
    "deducted_hours":"應扣除時間", "deduction_reason":"扣除原因",
    "cancel_date":"取消日期", "cancelled_sessions":"上課取消堂數", "reason":"取消原因",
    "project_name":"專案名稱", "person_name":"使用者", "item_name":"操作項目",
    "quantity":"數量", "item_hours":"每次時數", "execution_hours":"執行時數", "unit_price":"價格", "line_total":"總價",
    "funding_type":"專案類型", "stored_date":"儲值日期", "stored_amount":"儲值金額", "used_amount":"已使用金額", "remaining_amount":"剩餘金額", "line_amount":"金額", "active":"狀態",
    "trial_item_name":"體驗項目", "detail_content":"內容", "referral":"醫生轉介", "amount":"金額", "default_amount":"預設金額", "note":"備註",
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

def paged_rows(query_builder,page_size=1000):
    """分批讀取完整查詢結果，避免 Supabase Data API 單次回傳上限造成舊資料遺漏。"""
    result=[]; offset=0
    while True:
        page=rows(query_builder().range(offset,offset+page_size-1))
        result.extend(page)
        if len(page)<page_size: break
        offset+=page_size
    return result

def is_magnetic_wave_course(course_name):
    """課程名稱包含「動磁波」時，時數與一般銷課時數分開列示。"""
    return "動磁波" in str(course_name or "")

def is_magnetic_wave_operation(item):
    """體驗及單堂銷售以課程屬性或項目名稱判斷是否屬於動磁波。"""
    return any(is_magnetic_wave_course(item.get(field)) for field in ("course_type","content","item_name"))

def usage_sequence_by_date(usage_records):
    """依同一購買課程的銷課日期與建立順序，計算畫面應顯示的累計堂次。"""
    ordered=sorted(usage_records,key=lambda x:(str(x.get("usage_date") or ""),str(x.get("created_at") or ""),str(x.get("id") or "")))
    sequence_map={}
    counters={}
    for usage in ordered:
        purchase_id=usage.get("purchase_id")
        counters[purchase_id]=counters.get(purchase_id,0)+1
        sequence_map[usage.get("id")]=counters[purchase_id]
    return sequence_map

def course_status_label(item):
    """將課程資料庫狀態與實際銷課堂數轉為畫面使用的課程狀況。"""
    status=item.get("status")
    if status=="expired": return "逾期中止"
    if status=="cancelled": return "退費中止"
    used_sessions=int(item.get("used_sessions") or 0)
    total_sessions=int(item.get("total_sessions") or 0)
    remaining_sessions=float(item.get("remaining_sessions") or 0)
    if status=="completed" or remaining_sessions<=0 or (total_sessions>0 and used_sessions>=total_sessions):
        return "已完成"
    return "進行中"

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

def localize_usage_search_no_results():
    """只將銷課登錄會員／課程下拉搜尋的 No results 改為中文。"""
    components.html(
        """
        <script>
        (() => {
          const doc = window.parent.document;
          const targetLabels = ["會員名稱", "選擇課程", "輸入或選擇會員"];
          const isUsageSearch = () => {
            const active = doc.activeElement;
            if (!active) return false;
            const descriptor = [
              active.getAttribute("aria-label") || "",
              active.getAttribute("placeholder") || ""
            ].join(" ");
            return targetLabels.some(label => descriptor.includes(label));
          };
          const translate = () => {
            if (!isUsageSearch()) return;
            const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
              if (node.nodeValue && node.nodeValue.trim() === "No results") {
                node.nodeValue = node.nodeValue.replace("No results", "查無此人及課程");
              }
            }
          };
          const observer = new MutationObserver(translate);
          observer.observe(doc.body, {childList: true, subtree: true, characterData: true});
          doc.addEventListener("input", translate, true);
          translate();
        })();
        </script>
        """,
        height=0,
    )

def login():
    if "user" in st.session_state:
        return st.session_state.user
    st.title("秀傳運醫營運系統")
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
    # 所有教練下拉欄位僅顯示權限為 coach 的有效帳號。
    data = [x for x in data if x.get("role") == "coach"]
    return {x["display_name"]:x["id"] for x in data}

def show_table(data, columns=None):
    df = pd.DataFrame(data)
    if df.empty:
        st.info("目前沒有符合條件的資料。")
        return
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    display_df=df.rename(columns=LABELS)
    money_columns={LABELS.get(x,x) for x in ("total_amount","remaining_amount","deducted_amount","amount","unit_price","line_total","line_amount","price","stored_amount","used_amount")}
    money_config={x:st.column_config.NumberColumn(format="$ %.0f") for x in money_columns if x in display_df.columns}
    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config=money_config)

def daily_page(me):
    st.header("每日營運")
    coaches = coach_options()
    allowed = coaches if me["role"] in ("shared_coach","manager","admin") else {me["display_name"]:me["id"]}
    coach_date_limit={"min_value":date.today()} if me["role"]=="coach" else {}
    names={v:k for k,v in coaches.items()}
    tab1,tab2,tab3,tab4=st.tabs(["體驗項目","單堂銷售","活動支援","專案"])

    def standard_entry(tab, table_name, form_key, content_label, catalog_type, member_label=None):
        with tab:
            catalog_query=client().table("operation_item_catalog").select("id,item_name,detail_content,course_type,session_hours,default_amount,active").eq("item_type",catalog_type)
            if catalog_type=="trial": catalog_query=catalog_query.eq("active",True)
            catalog=rows(catalog_query.order("item_name"))
            option_map={
                (f'{x["item_name"]}｜{x.get("detail_content") or ""}' if catalog_type=="trial" else x["item_name"]):x
                for x in catalog
            }
            if not option_map:
                st.warning(f"尚未建立{content_label}選項，請由系統管理員到「資料管理」新增。")
                return
            revision_key=f"{form_key}_revision"
            revision=st.session_state.get(revision_key,0)
            selected_option=st.selectbox(content_label,list(option_map),index=None,placeholder=f"請選擇{content_label}",key=f"{form_key}_content_{revision}")
            selected_catalog=option_map.get(selected_option) if selected_option else None
            content=selected_catalog.get("item_name") if selected_catalog else None
            course_type=(selected_catalog.get("course_type") or "").strip() if selected_catalog else None
            default_hours=float(selected_catalog.get("session_hours") or 1) if selected_catalog else None
            default_amount=float(selected_catalog.get("default_amount") or 0) if selected_catalog else None
            default_detail=str(selected_catalog.get("detail_content") or "") if selected_catalog else ""
            with st.form(f"{form_key}_{revision}",clear_on_submit=True,enter_to_submit=False):
                c1,c2=st.columns(2); entry_date=c1.date_input("日期",date.today(),**coach_date_limit); coach_name=c2.selectbox("教練",list(allowed),index=None,placeholder="請選擇教練")
                member_name=st.text_input(member_label) if member_label else None
                detail_content=st.text_input("內容",value=default_detail,disabled=True) if catalog_type=="trial" else None
                c1,c2=st.columns(2)
                hours=c1.number_input("時數",0.25,24.0,value=default_hours,step=0.25,placeholder="選擇內容後自動帶入",disabled=True)
                amount=c2.number_input("金額",0.0,1000000000.0,value=default_amount,step=100.0,format="%.0f",placeholder="選擇內容後自動帶入")
                note=st.text_input("備註")
                record_name="體驗項目" if catalog_type=="trial" else "單堂銷售"
                save=st.form_submit_button(f"確認並建立{record_name}紀錄",type="primary",use_container_width=True)
            if save:
                errors=[]
                if member_label and not member_name.strip(): errors.append(f"{member_label}不可空白")
                if me["role"]=="coach" and entry_date<date.today(): errors.append("教練只能填寫今天或未來日期")
                if coach_name is None: errors.append("請選擇教練")
                if content is None: errors.append(f"請選擇{content_label}")
                if content is not None and not course_type: errors.append("此項目尚未設定課程屬性，請由系統管理員先完成設定")
                if hours is None: errors.append("請先選擇內容以帶入時數")
                if errors:
                    st.error("；".join(errors)+"。")
                else:
                    try:
                        payload={"entry_date":str(entry_date),"content":content,"course_type":course_type,"hours":hours,"amount":amount,"note":note.strip() or None,"coach_id":allowed[coach_name],"created_by":me["id"]}
                        if catalog_type=="trial": payload["detail_content"]=detail_content.strip() or None
                        if member_label: payload["member_name"]=member_name.strip()
                        client().table(table_name).insert(payload).execute()
                        st.session_state[revision_key]=revision+1
                        st.success("紀錄已新增。"); st.rerun()
                    except Exception as exc: st.error(f"新增失敗：{exc}")
            select_fields="entry_date,content,detail_content,hours,amount,note,coach_id,member_name" if catalog_type=="trial" else ("entry_date,content,hours,amount,note,coach_id,member_name" if member_label else "entry_date,content,hours,amount,note,coach_id")
            data=rows(client().table(table_name).select(select_fields).order("entry_date",desc=True).limit(100))
            data=[x for x in data if x.get("coach_id")==me["id"]] if me["role"]=="coach" else [x for x in data if x.get("coach_id") in names]
            for x in data:
                x["coach_name"]=names.get(x.pop("coach_id"),"未知")
                if member_label:
                    display_member_key="trial_member_name" if catalog_type=="trial" else "single_sale_member_name"
                    x[display_member_key]=x.pop("member_name",None)
                if catalog_type=="trial": x["trial_item_name"]=x.pop("content",None)
            member_column=["trial_member_name" if catalog_type=="trial" else "single_sale_member_name"] if member_label else []
            content_columns=["trial_item_name","detail_content"] if catalog_type=="trial" else ["content"]
            columns=["entry_date"] + member_column + content_columns + ["hours","amount","coach_name","note"]
            show_table(data,columns)

    standard_entry(tab1,"trial_items","trial_item_form","體驗項目","trial",member_label="體驗會員姓名")
    standard_entry(tab2,"single_sales","single_sale_form","銷售內容","single_sale",member_label="單堂銷售會員姓名")
    with tab3:
        with st.form("event_support_form",clear_on_submit=True,enter_to_submit=False):
            c1,c2=st.columns(2); entry_date=c1.date_input("日期",date.today(),key="event_date"); coach_name=c2.selectbox("教練",list(allowed),index=None,placeholder="請選擇教練",key="event_coach")
            content=st.text_input("活動內容")
            c1,c2=st.columns(2); hours=c1.number_input("時數",0.25,24.0,value=None,step=0.25,placeholder="請輸入時數",key="event_hours"); deducted_hours=c2.number_input("應扣除時間",0.0,24.0,0.0,step=0.25)
            reason=st.text_input("扣除原因"); save=st.form_submit_button("確認並建立活動支援紀錄",type="primary",use_container_width=True)
        if save:
            if coach_name is None: st.error("請選擇教練。")
            elif not content.strip(): st.error("活動內容不可空白。")
            elif hours is None: st.error("請輸入時數。")
            elif deducted_hours>hours: st.error("應扣除時間不可大於活動時數。")
            elif deducted_hours>0 and not reason.strip(): st.error("有扣除時間時必須填寫扣除原因。")
            else:
                try:
                    client().table("event_supports").insert({"entry_date":str(entry_date),"content":content.strip(),"hours":hours,"coach_id":allowed[coach_name],"deducted_hours":deducted_hours,"deduction_reason":reason.strip() or None,"created_by":me["id"]}).execute()
                    st.success("紀錄已新增。"); st.rerun()
                except Exception as exc: st.error(f"新增失敗：{exc}")
        data=rows(client().table("event_supports").select("entry_date,content,hours,deducted_hours,deduction_reason,coach_id").order("entry_date",desc=True).limit(100))
        data=[x for x in data if x.get("coach_id")==me["id"]] if me["role"]=="coach" else [x for x in data if x.get("coach_id") in names]
        for x in data: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
        show_table(data,["entry_date","content","coach_name","hours","deducted_hours","deduction_reason"])

    with tab4:
        try:
            projects=rows(client().table("projects").select("id,project_name,funding_type,stored_amount").eq("active",True).order("project_name"))
            catalog=rows(client().table("project_catalog").select("id,project_id,project_name,item_name,hours,price").order("project_name").order("item_name"))
        except Exception:
            st.warning("專案主檔尚未建立，請系統管理員先執行 migration_project_v1_1_0.sql。")
            projects=[]
            catalog=[]
        if not catalog:
            st.warning("尚未建立專案項目，請由系統管理員到「資料管理 → 專案管理」新增。")
        else:
            project_map={x["project_name"]:x for x in projects}
            project_names=[x for x in project_map if any(item.get("project_id")==project_map[x]["id"] for item in catalog)]
            project_name=st.selectbox("專案名稱",project_names,index=None,placeholder="請選擇專案",key="project_entry_project")
            selected_project=project_map.get(project_name)
            project_items=[x for x in catalog if selected_project and x.get("project_id")==selected_project["id"]]
            item_labels={f'{x["item_name"]}｜{float(x["hours"]):g} 小時｜$ {float(x["price"]):,.0f}':x for x in project_items}
            item_label=st.selectbox("操作項目",list(item_labels),index=None,placeholder="請選擇操作項目",key="project_entry_item")
            selected_item=item_labels.get(item_label)
            form_key=f'project_entry_{selected_item["id"] if selected_item else "empty"}'
            c1,c2=st.columns(2)
            quantity=c1.number_input("數量",0.01,100000.0,value=1.0,step=1.0,key=f'{form_key}_quantity')
            suggested_total=(float(selected_item["price"])*quantity) if selected_item else 0.0
            price_key=f'{form_key}_total_{quantity:g}'
            total_price=c2.number_input("價格",0.0,1000000000.0,value=suggested_total,step=100.0,format="%.0f",key=price_key,
                help="預設為操作項目單價 × 數量，仍可自行修改。")
            if selected_item:
                st.caption(f'項目時數：{float(selected_item["hours"]):g} 小時／次｜項目單價：$ {float(selected_item["price"]):,.0f}｜本筆價格：$ {total_price:,.0f}')
            if selected_project:
                if selected_project["funding_type"]=="stored":
                    balance=rows(client().rpc("get_project_funding_status",{"p_project_id":selected_project["id"]}))
                    remaining=float(balance[0]["remaining_amount"]) if balance else float(selected_project["stored_amount"])
                    st.info(f'專案類型：已儲值｜儲值金額：$ {float(selected_project["stored_amount"]):,.0f}｜目前剩餘：$ {remaining:,.0f}')
                else:
                    st.info("專案類型：未儲值（事後請款）")
            with st.form(form_key,clear_on_submit=True,enter_to_submit=False):
                c1,c2=st.columns(2)
                project_date=c1.date_input("日期",date.today())
                person_name=c2.text_input("使用者")
                coach_name=st.selectbox("教練",list(allowed),index=None,placeholder="請選擇教練",key=f'{form_key}_coach')
                project_note=st.text_input("備註")
                add_project=st.form_submit_button("確認並建立專案紀錄",type="primary",use_container_width=True)
            if add_project:
                if selected_item is None: st.error("請選擇專案及操作項目。")
                elif not person_name.strip(): st.error("使用者不可空白。")
                elif not coach_name: st.error("請選擇教練。")
                else:
                    try:
                        client().rpc("create_project_operation",{"p_entry_date":str(project_date),"p_catalog_id":selected_item["id"],
                            "p_user_name":person_name.strip(),"p_coach_id":allowed[coach_name],"p_quantity":quantity,
                            "p_total_amount":total_price,"p_note":project_note.strip() or None}).execute()
                        st.success("專案紀錄已建立。"); st.rerun()
                    except Exception as exc: st.error(f"新增失敗：{exc}")
            project_rows=rows(client().table("project_entries").select("entry_date,project_name,person_name,coach_id,item_name,item_hours,quantity,unit_price,line_amount,note").order("entry_date",desc=True).limit(100))
            project_rows=[x for x in project_rows if x.get("coach_id")==me["id"]] if me["role"]=="coach" else [x for x in project_rows if x.get("coach_id") in names]
            for row in project_rows:
                row["coach_name"]=names.get(row.pop("coach_id"),"未知")
                row["execution_hours"]=float(row.get("item_hours") or 0)*float(row["quantity"])
                row["line_total"]=float(row["line_amount"])
            show_table(project_rows,["entry_date","project_name","person_name","coach_name","item_name","item_hours","quantity","execution_hours","unit_price","line_total","note"])

def purchase_page(me):
    st.header("課程購買")
    coaches=coach_options(); allowed=coaches if me["role"] in ("shared_coach","manager","admin") else {me["display_name"]:me["id"]}
    coach_date_limit={"min_value":date.today()} if me["role"]=="coach" else {}
    courses=rows(client().table("course_catalog").select("course_name,course_type,session_hours").eq("active",True).order("course_name"))
    course_options={f'{x.get("course_type") or "未分類"}｜{x["course_name"]}':x["course_name"] for x in courses}
    course_names=list(course_options)
    course_hours={x["course_name"]:float(x.get("session_hours") or 1) for x in courses}
    if not course_names:
        st.warning("尚未建立課程名稱，請由系統管理員先到「課程名稱管理」新增。")
        return
    purchase_revision_key="purchase_form_revision"
    purchase_revision=st.session_state.get(purchase_revision_key,0)
    c1,c2=st.columns(2)
    plan=c1.selectbox("付款方式",["未分期","分期"],index=None,placeholder="請選擇付款方式",key=f"purchase_payment_plan_{purchase_revision}")
    course_label=c2.selectbox("課程名稱",course_names,index=None,placeholder="請選擇課程",key=f"purchase_course_{purchase_revision}")
    course=course_options.get(course_label) if course_label else None
    selected_session_hours=course_hours.get(course) if course else None
    with st.form(f"purchase_{purchase_revision}",clear_on_submit=True,enter_to_submit=False):
        c1,c2,c3=st.columns(3)
        member_name=c1.text_input("會員名稱（需完整一致）")
        kind=c2.selectbox("購買類型",["首次購買","續課"])
        coach_name=c3.selectbox("指導教練",list(allowed),index=None,placeholder="請選擇教練")
        c1,c2,c3=st.columns(3)
        sessions=c1.number_input("課程堂數",1,999,value=None,placeholder="請輸入堂數")
        session_hours=c2.number_input("每堂課時數",0.25,24.0,value=selected_session_hours,step=0.25,format="%.2f",placeholder="選擇課程後自動帶入",disabled=True)
        amount=c3.number_input("成交總金額",0.0,10000000.0,value=None,step=100.0,format="%.0f",placeholder="請輸入金額")
        c1,c2=st.columns(2)
        purchased=c1.date_input("購買日期",date.today(),**coach_date_limit)
        try:
            default_expiry=purchased.replace(year=purchased.year+1)
        except ValueError:
            default_expiry=purchased.replace(year=purchased.year+1,day=28)
        expiry=c2.date_input("有效日期",value=default_expiry)
        referral=st.text_input("醫生轉介")
        purchase_note=st.text_area("備註")
        if plan=="分期":
            count=st.selectbox("總期數",[2,3],index=None,placeholder="請選擇總期數")
            c1,c2,c3=st.columns(3)
            installment_no=c1.number_input("此次為第幾期",value=1,disabled=True)
            paid=c2.number_input("此次支付金額",0.0,10000000.0,value=None,step=100.0,format="%.0f",placeholder="請輸入支付金額")
            paid_date=c3.date_input("支付日期",date.today(),**coach_date_limit)
        elif plan=="未分期":
            count=1
            installment_no=1
            paid=amount
            paid_date=purchased
            st.caption("未分期將於建立紀錄時，自動以成交總金額記錄為一次付清。")
        else:
            count=installment_no=paid=paid_date=None
        save=st.form_submit_button("確認並建立購買紀錄",type="primary",use_container_width=True)
    if save:
        errors=[]
        if not member_name.strip(): errors.append("會員名稱不可空白")
        if coach_name is None: errors.append("請選擇指導教練")
        if course is None: errors.append("請選擇課程名稱")
        if sessions is None: errors.append("請輸入課程堂數")
        if session_hours is None: errors.append("請選擇課程以帶入每堂課時數")
        if amount is None: errors.append("請輸入成交總金額")
        if expiry is None: errors.append("請選擇有效日期")
        elif expiry<purchased: errors.append("有效日期不可早於購買日期")
        if me["role"]=="coach" and purchased<date.today(): errors.append("教練的購買日期只能填寫今天或未來日期")
        if me["role"]=="coach" and paid_date is not None and paid_date<date.today(): errors.append("教練的支付日期只能填寫今天或未來日期")
        if plan is None: errors.append("請選擇付款方式")
        if plan=="分期" and count is None: errors.append("請選擇總期數")
        if paid is None or paid<=0: errors.append("此次支付金額須大於 0")
        if paid is not None and amount is not None and paid>amount: errors.append("此次支付金額不可大於成交總金額")
        if installment_no is not None and installment_no!=1: errors.append("新購買紀錄應先登錄第 1 期；後續期款請由付款功能登錄")
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
                    "installment_count":count,"referral":referral.strip() or None,"note":purchase_note.strip() or None,"created_by":me["id"]}))[0]
                client().table("purchase_payments").insert({"purchase_id":p["id"],"installment_no":1,"amount":paid,"paid_date":str(paid_date),"created_by":me["id"]}).execute()
                st.session_state[purchase_revision_key]=purchase_revision+1
                st.success("購買與首期付款紀錄已建立。"); st.rerun()
            except Exception as exc: st.error(f"建立失敗：{exc}")
    purchases=rows(client().table("purchase_balances").select("purchase_id,member_name,course_name,coach_id"))
    operational_ids=set(coaches.values())
    purchases=[x for x in purchases if x.get("coach_id")==me["id"]] if me["role"]=="coach" else [x for x in purchases if x.get("coach_id") in operational_ids]
    installment_rows=rows(client().table("purchases").select("id,total_amount,installment_count").eq("payment_plan","installment"))
    installment_map={x["id"]:x for x in installment_rows}
    all_purchase_keys=rows(client().table("purchases").select("id,purchase_date,created_at"))
    installment_code_map=_build_purchase_code_map(all_purchase_keys)
    installment_ids=set(installment_map)
    payment_rows=rows(client().table("purchase_payments").select("purchase_id,installment_no,amount").in_("purchase_id",list(installment_ids))) if installment_ids else []
    payment_summary={}
    for payment in payment_rows:
        summary=payment_summary.setdefault(payment["purchase_id"],{"amount":0.0,"numbers":set()})
        summary["amount"]+=float(payment["amount"])
        summary["numbers"].add(int(payment["installment_no"]))
    lookup={}
    for purchase in purchases:
        plan=installment_map.get(purchase["purchase_id"])
        if not plan:
            continue
        paid=payment_summary.get(purchase["purchase_id"],{"amount":0.0,"numbers":set()})
        if paid["amount"]>=float(plan["total_amount"]):
            continue
        unpaid_amount=max(float(plan["total_amount"])-paid["amount"],0)
        purchase_code=installment_code_map.get(purchase["purchase_id"],purchase["purchase_id"])
        lookup[f'{purchase_code}｜{purchase["member_name"]}｜{purchase["course_name"]}｜{int(plan["installment_count"])} 期｜未付 $ {unpaid_amount:,.0f}']={
            "id":purchase["purchase_id"],"purchase_code":purchase_code,"paid_numbers":paid["numbers"],"unpaid_amount":unpaid_amount}
    if lookup:
        st.subheader("登錄後續期款")
        with st.form("payment"):
            label=st.selectbox("購買紀錄",list(lookup))
            selected_payment=lookup[label]
            c1,c2,c3=st.columns(3)
            installment_choice=c1.selectbox("期次",["第 2 期","第 3 期"])
            pay_amount=c2.number_input("支付金額",1.0,10000000.0,step=100.0,format="%.0f")
            pay_date=c3.date_input("付款日期",date.today())
            no=2 if installment_choice=="第 2 期" else 3
            st.caption(f'本次付款沿用購買課程編號：{selected_payment["purchase_code"]}；不會建立新的 purchase_id。')
            add=st.form_submit_button("新增付款")
        if add:
            try:
                if int(no) in selected_payment["paid_numbers"]:
                    raise ValueError(f"第 {int(no)} 期已登錄，不可重複")
                if float(pay_amount)>float(selected_payment["unpaid_amount"]):
                    raise ValueError("支付金額不可超過未付金額")
                client().table("purchase_payments").insert({"purchase_id":selected_payment["id"],"installment_no":no,"amount":pay_amount,"paid_date":str(pay_date),"created_by":me["id"]}).execute()
                st.success("付款紀錄已新增。")
                st.rerun()
            except Exception as exc: st.error(f"新增失敗（請檢查期次是否重複或超出設定）：{exc}")

def usage_query_tabs(me, enable_export=False, purchase_code_map=None):
    st.divider()
    st.subheader("教練查詢")
    export_sheets={}
    coaches=coach_options()
    operational_ids=set(coaches.values())
    balances=rows(client().table("purchase_balances").select("*").order("expiry_date"))
    balances=[x for x in balances if x.get("coach_id") in operational_ids]
    if me["role"]=="coach":
        balances=[x for x in balances if x.get("coach_id")==me["id"]]
    purchase_ids=[x["purchase_id"] for x in balances]
    purchases=[]
    payments=[]
    if purchase_ids:
        purchases=rows(client().table("purchases").select("id,payment_plan,installment_count,session_hours,purchase_date,course_name").in_("id",purchase_ids))
        payments=rows(client().table("purchase_payments").select("purchase_id,installment_no,amount").in_("purchase_id",purchase_ids))
    purchase_map={x["id"]:x for x in purchases}
    if purchase_code_map is None:
        all_purchase_keys=paged_rows(lambda: client().table("purchases").select("id,purchase_date,created_at")
            .order("purchase_date").order("created_at").order("id"))
        purchase_code_map=_build_purchase_code_map(all_purchase_keys)
    for balance in balances:
        balance["purchase_date"]=purchase_map.get(balance["purchase_id"],{}).get("purchase_date")
    balances.sort(key=lambda x:str(x.get("purchase_date") or ""),reverse=True)
    payment_map={}
    for payment in payments:
        summary=payment_map.setdefault(payment["purchase_id"],{"amount":0.0,"count":0})
        summary["amount"]+=float(payment["amount"])
        summary["count"]+=1

    def course_is_completed(item):
        remaining_sessions=float(item.get("remaining_sessions") or 0)
        used_sessions=int(item.get("used_sessions") or 0)
        total_sessions=int(item.get("total_sessions") or 0)
        return (item.get("status")=="completed" or remaining_sessions<=0
            or (total_sessions>0 and used_sessions>=total_sessions))

    tab1,tab2,tab3,tab4,tab5=st.tabs(["會員課程查詢","執行時數","即將到期／過期","剩餘三堂（含）","銷課明細查詢"])
    with tab1:
        can_filter_coach=me["role"] in ("shared_coach","manager","admin")
        if can_filter_coach:
            filter_col1,filter_col2,filter_col3=st.columns(3)
            selected_coach=filter_col1.selectbox("成交教練",["全部教練"]+list(coaches),key="member_course_coach_filter")
            member_keyword=filter_col2.text_input("會員名稱",placeholder="輸入完整或部分會員名稱",key="member_course_name_filter").strip()
            course_end_filter=filter_col3.selectbox("課程狀況",["全部","進行中","已完成","逾期中止","退費中止"],key="member_course_end_filter")
            filtered_balances=balances if selected_coach=="全部教練" else [x for x in balances if x.get("coach_id")==coaches[selected_coach]]
        else:
            filter_col1,filter_col2,filter_col3=st.columns(3)
            filter_col1.caption(f'成交教練：{me["display_name"]}')
            member_keyword=filter_col2.text_input("會員名稱",placeholder="輸入完整或部分會員名稱",key="member_course_name_filter").strip()
            course_end_filter=filter_col3.selectbox("課程狀況",["全部","進行中","已完成","逾期中止","退費中止"],key="member_course_end_filter")
            filtered_balances=[x for x in balances if x.get("coach_id")==me["id"]]
        if member_keyword:
            normalized_keyword=member_keyword.casefold()
            filtered_balances=[x for x in filtered_balances if normalized_keyword in str(x.get("member_name") or "").casefold()]
        if course_end_filter!="全部": filtered_balances=[x for x in filtered_balances if course_status_label(x)==course_end_filter]
        detail=[]
        for item in filtered_balances:
            purchase=purchase_map.get(item["purchase_id"],{})
            payment=payment_map.get(item["purchase_id"],{"amount":0.0,"count":0})
            total_amount=float(item["total_amount"])
            used_sessions=int(item.get("used_sessions") or 0)
            total_sessions=int(item.get("total_sessions") or 0)
            if payment["amount"] >= total_amount:
                payment_status="已付清"
            elif purchase.get("payment_plan")=="installment":
                payment_status=f'已付 {payment["count"]}/{purchase.get("installment_count", "-")} 期，$ {payment["amount"]:,.0f}'
            else:
                payment_status=f'尚欠 $ {total_amount-payment["amount"]:,.0f}'
            course_status=course_status_label(item)
            detail.append({
                "購買_ID":purchase_code_map.get(item["purchase_id"],item["purchase_id"]),
                "教練":item.get("coach_name") or "未知教練","會員名稱":item["member_name"],"課程名稱":item["course_name"],
                "時數":float(purchase.get("session_hours") or 1),"成交金額":total_amount,
                "剩餘金額":float(item["remaining_amount"]),"堂數":f"{used_sessions}／{total_sessions}",
                "有效期限":item["expiry_date"],"付款狀況":payment_status,"課程狀況":course_status,
            })
        detail_columns=["購買_ID","教練","會員名稱","課程名稱","時數","成交金額","剩餘金額","堂數","有效期限","付款狀況","課程狀況"]
        member_course_df=pd.DataFrame(detail,columns=detail_columns)
        export_sheets["會員課程查詢"]=member_course_df
        if detail:
            st.dataframe(member_course_df,hide_index=True,width="stretch",height="auto",row_height=28,
                column_config={
                    "購買_ID":st.column_config.TextColumn(width=105),
                    "教練":st.column_config.TextColumn(width=70),
                    "會員名稱":st.column_config.TextColumn(width=85),
                    "課程名稱":st.column_config.TextColumn(width=95),
                    "時數":st.column_config.NumberColumn(format="%.2f",width=55),
                    "成交金額":st.column_config.NumberColumn(format="$ %.0f",width=85),
                    "剩餘金額":st.column_config.NumberColumn(format="$ %.0f",width=85),
                    "堂數":st.column_config.TextColumn(width=65),
                    "有效期限":st.column_config.TextColumn(width=90),
                    "付款狀況":st.column_config.TextColumn(width=115),
                    "課程狀況":st.column_config.TextColumn(width=80),
                })
        else:
            st.info("目前沒有可查詢的課程資料。")

    with tab2:
        usage_detail_display=pd.DataFrame(columns=["日期","教練","會員名稱","課程名稱","銷課時數","動磁波時數","銷課金額"])
        daily_hours_df=pd.DataFrame(columns=["日期","教練","體驗項目時數","單堂銷售時數","專案時數","活動支援時數（扣除後÷2）","每日營運時數合計"])
        c1,c2,c3=st.columns(3)
        query_start=c1.date_input("開始日期",date.today().replace(day=1),key="usage_query_start")
        query_end=c2.date_input("結束日期",date.today(),key="usage_query_end")
        if can_filter_coach:
            usage_coach=c3.selectbox("授課教練",["全部教練"]+list(coaches),key="usage_stats_coach_filter")
        else:
            c3.caption(f'授課教練：{me["display_name"]}')
            usage_coach=me["display_name"]
        if query_start>query_end:
            st.error("開始日期不可晚於結束日期。")
        else:
            usages=rows(client().table("session_usages").select("purchase_id,usage_date,coach_id,deducted_amount").gte("usage_date",str(query_start)).lte("usage_date",str(query_end)).order("usage_date",desc=True))
            usages=[x for x in usages if x.get("coach_id") in operational_ids]
            trial_hours=rows(client().table("trial_items").select("coach_id,hours,entry_date").gte("entry_date",str(query_start)).lte("entry_date",str(query_end)))
            single_hours=rows(client().table("single_sales").select("coach_id,hours,entry_date").gte("entry_date",str(query_start)).lte("entry_date",str(query_end)))
            event_hours=rows(client().table("event_supports").select("coach_id,hours,deducted_hours,entry_date").gte("entry_date",str(query_start)).lte("entry_date",str(query_end)))
            project_hours=rows(client().table("project_entries").select("coach_id,item_hours,quantity,entry_date").gte("entry_date",str(query_start)).lte("entry_date",str(query_end)))
            trial_hours=[x for x in trial_hours if x.get("coach_id") in operational_ids]
            single_hours=[x for x in single_hours if x.get("coach_id") in operational_ids]
            event_hours=[x for x in event_hours if x.get("coach_id") in operational_ids]
            project_hours=[x for x in project_hours if x.get("coach_id") in operational_ids]
            if usage_coach!="全部教練":
                usage_coach_id=coaches.get(usage_coach,me["id"])
                usages=[x for x in usages if x.get("coach_id")==usage_coach_id]
                trial_hours=[x for x in trial_hours if x.get("coach_id")==usage_coach_id]
                single_hours=[x for x in single_hours if x.get("coach_id")==usage_coach_id]
                event_hours=[x for x in event_hours if x.get("coach_id")==usage_coach_id]
                project_hours=[x for x in project_hours if x.get("coach_id")==usage_coach_id]
            balance_by_purchase={x["purchase_id"]:x for x in balances}
            usage_detail=[]
            total_usage_hours=0.0
            total_magnetic_wave_hours=0.0
            for usage in usages:
                purchase=purchase_map.get(usage["purchase_id"],{})
                session_hours=float(purchase.get("session_hours") or 1)
                course_name=purchase.get("course_name") or balance_by_purchase.get(usage["purchase_id"],{}).get("course_name","")
                magnetic_wave_hours=session_hours if is_magnetic_wave_course(course_name) else 0.0
                regular_usage_hours=0.0 if magnetic_wave_hours else session_hours
                total_usage_hours+=regular_usage_hours
                total_magnetic_wave_hours+=magnetic_wave_hours
                usage_detail.append({"日期":usage["usage_date"],"教練":next((name for name,cid in coaches.items() if cid==usage["coach_id"]),"未知"),
                    "會員名稱":balance_by_purchase.get(usage["purchase_id"],{}).get("member_name","未知"),
                    "課程名稱":course_name,"銷課時數":regular_usage_hours,"動磁波時數":magnetic_wave_hours,
                    "銷課金額":float(usage["deducted_amount"])})
            total_amount=sum(float(x["deducted_amount"]) for x in usages)
            total_daily_hours=(sum(float(x["hours"]) for x in trial_hours)
                +sum(float(x["hours"]) for x in single_hours)
                +sum((float(x["hours"])-float(x.get("deducted_hours") or 0))/2 for x in event_hours)
                +sum(float(x.get("item_hours") or 0)*float(x["quantity"]) for x in project_hours))
            total_execution_hours=total_usage_hours+total_magnetic_wave_hours+total_daily_hours
            a,b,c,d=st.columns(4)
            a.metric("銷課時數",f"{total_usage_hours:,.2f} 小時")
            b.metric("動磁波時數",f"{total_magnetic_wave_hours:,.2f} 小時")
            c.metric("每日營運時數",f"{total_daily_hours:,.2f} 小時")
            d.metric("總執行時數",f"{total_execution_hours:,.2f} 小時")
            execution_tabs=st.tabs(["銷課時數","每日營運時數"])
            with execution_tabs[0]:
                if usage_detail:
                    usage_detail_display=pd.DataFrame(usage_detail,columns=["日期","教練","會員名稱","課程名稱","銷課時數","動磁波時數","銷課金額"])
                    usage_detail_display=pd.concat([usage_detail_display,pd.DataFrame([{
                        "日期":"合計","教練":"","會員名稱":"","課程名稱":"","銷課時數":total_usage_hours,
                        "動磁波時數":total_magnetic_wave_hours,"銷課金額":total_amount}])],ignore_index=True)
                    st.dataframe(usage_detail_display,hide_index=True,use_container_width=True,
                        column_config={"銷課時數":st.column_config.NumberColumn(format="%.2f 小時"),
                            "動磁波時數":st.column_config.NumberColumn(format="%.2f 小時"),"銷課金額":st.column_config.NumberColumn(format="$ %.0f")})
                else: st.info("查詢期間沒有銷課時數資料。")
            with execution_tabs[1]:
                daily_keys=sorted({(str(x["entry_date"]),x["coach_id"]) for group in (trial_hours,single_hours,event_hours,project_hours) for x in group},reverse=True)
                daily_rows=[]
                coach_name_by_id={cid:name for name,cid in coaches.items()}
                for entry_date,coach_id in daily_keys:
                    trial_total=sum(float(x["hours"]) for x in trial_hours if str(x["entry_date"])==entry_date and x["coach_id"]==coach_id)
                    single_total=sum(float(x["hours"]) for x in single_hours if str(x["entry_date"])==entry_date and x["coach_id"]==coach_id)
                    project_total=sum(float(x.get("item_hours") or 0)*float(x["quantity"]) for x in project_hours if str(x["entry_date"])==entry_date and x["coach_id"]==coach_id)
                    event_total=sum((float(x["hours"])-float(x.get("deducted_hours") or 0))/2 for x in event_hours if str(x["entry_date"])==entry_date and x["coach_id"]==coach_id)
                    daily_rows.append({"日期":entry_date,"教練":coach_name_by_id.get(coach_id,"未知"),"體驗項目時數":trial_total,
                        "單堂銷售時數":single_total,"專案時數":project_total,"活動支援時數（扣除後÷2）":event_total,
                        "每日營運時數合計":trial_total+single_total+project_total+event_total})
                if daily_rows:
                    daily_hours_df=pd.DataFrame(daily_rows)
                    daily_hour_columns={name:st.column_config.NumberColumn(format="%.2f 小時") for name in ["體驗項目時數","單堂銷售時數","專案時數","活動支援時數（扣除後÷2）","每日營運時數合計"]}
                    st.dataframe(daily_hours_df,hide_index=True,use_container_width=True,column_config=daily_hour_columns)
                else: st.info("查詢期間沒有每日營運時數資料。")
        export_sheets["執行時數_銷課"]=usage_detail_display
        export_sheets["執行時數_每日營運"]=daily_hours_df

    with tab3:
        today=date.today()
        deadline=today+timedelta(days=30)
        expiring=[x for x in balances if course_status_label(x)=="進行中" and x.get("expiry_date")
            and pd.to_datetime(x["expiry_date"]).date()<=deadline]
        if expiring:
            expiry_rows=[]
            for x in expiring:
                expiry_date=pd.to_datetime(x["expiry_date"]).date()
                expiry_rows.append({"購買_ID":purchase_code_map.get(x["purchase_id"],x["purchase_id"]),
                    "教練":x["coach_name"],"會員名稱":x["member_name"],"課程名稱":x["course_name"],
                    "有效期限":x["expiry_date"],"即將到期":"是" if today<=expiry_date<=deadline else "否",
                    "過期":"是" if expiry_date<today else "否"})
            expiry_columns=["購買_ID","教練","會員名稱","課程名稱","有效期限","即將到期","過期"]
            expiry_df=pd.DataFrame(expiry_rows,columns=expiry_columns)
            st.dataframe(expiry_df,hide_index=True,width="stretch")
        else:
            expiry_df=pd.DataFrame(columns=["購買_ID","教練","會員名稱","課程名稱","有效期限","即將到期","過期"])
            st.info("目前沒有即將到期或過期的課程資料。")
        export_sheets["即將到期過期"]=expiry_df

    with tab4:
        low_balances=[x for x in balances if not course_is_completed(x) and x["status"]=="active"
            and 0<float(x["remaining_sessions"])<=3]
        if low_balances:
            low_rows=[{
                "購買_ID":purchase_code_map.get(x["purchase_id"],x["purchase_id"]),
                "教練":x.get("coach_name") or "未知教練",
                "會員名稱":x["member_name"],
                "課程名稱":x["course_name"],
                "堂數":f'{int(x.get("used_sessions") or 0)}／{int(x.get("total_sessions") or 0)}',
                "有效期限":x["expiry_date"],
            } for x in low_balances]
            low_balance_df=pd.DataFrame(low_rows,columns=["購買_ID","教練","會員名稱","課程名稱","堂數","有效期限"])
            st.dataframe(low_balance_df,hide_index=True,width="stretch")
        else:
            low_balance_df=pd.DataFrame(columns=["購買_ID","教練","會員名稱","課程名稱","堂數","有效期限"])
            st.info("目前沒有剩餘三堂（含）以下的有效課程。")
        export_sheets["剩餘三堂"]=low_balance_df

    with tab5:
        detail_c1,detail_c2=st.columns(2)
        if can_filter_coach:
            detail_coach=detail_c1.selectbox("成交教練",["全部教練"]+list(coaches),key="usage_detail_coach")
        else:
            detail_c1.caption(f'成交教練：{me["display_name"]}')
            detail_coach=me["display_name"]
        detail_member_keyword=detail_c2.text_input("會員名稱",placeholder="輸入完整或部分會員名稱",key="usage_detail_member").strip()
        detail_balances=balances
        if detail_coach!="全部教練":
            detail_coach_id=coaches.get(detail_coach,me["id"])
            detail_balances=[x for x in detail_balances if x.get("coach_id")==detail_coach_id]
        if detail_member_keyword:
            detail_member_key=detail_member_keyword.casefold()
            detail_balances=[x for x in detail_balances if detail_member_key in str(x.get("member_name") or "").casefold()]
        detail_balance_map={x["purchase_id"]:x for x in detail_balances}
        detail_purchase_ids=list(detail_balance_map)
        detail_usages=(paged_rows(lambda: client().table("session_usages").select("id,purchase_id,usage_date,session_seq,coach_id,note,created_at")
            .in_("purchase_id",detail_purchase_ids).order("usage_date").order("created_at").order("id")) if detail_purchase_ids else [])
        displayed_sequence=usage_sequence_by_date(detail_usages)
        detail_usages.sort(key=lambda x:(str(x.get("usage_date") or ""),str(x.get("created_at") or ""),str(x.get("id") or "")),reverse=True)
        usage_detail_rows=[]
        for usage in detail_usages:
            balance=detail_balance_map.get(usage["purchase_id"],{})
            used_session_count=displayed_sequence.get(usage.get("id"),int(usage.get("session_seq") or 0))
            total_session_count=int(balance.get("total_sessions") or 0)
            usage_detail_rows.append({"購買_ID":purchase_code_map.get(usage["purchase_id"],usage["purchase_id"]),
                "教練":next((name for name,coach_id in coaches.items() if coach_id==usage.get("coach_id")),"未知教練"),
                "會員名稱":balance.get("member_name",""),"課程名稱":balance.get("course_name",""),
                "銷課日期":usage["usage_date"],"堂數":f"{used_session_count}／{total_session_count}",
                "有效期限":balance.get("expiry_date")})
        usage_detail_columns=["購買_ID","教練","會員名稱","課程名稱","銷課日期","堂數","有效期限"]
        usage_history_df=pd.DataFrame(usage_detail_rows,columns=usage_detail_columns)
        export_sheets["銷課明細查詢"]=usage_history_df
        if usage_detail_rows:
            st.dataframe(usage_history_df,hide_index=True,width="stretch")
        else:
            st.info("目前沒有符合條件的銷課明細。")

    if enable_export:
        coach_query_export=_excel_bytes(export_sheets)
        st.download_button("下載教練查詢報表",coach_query_export,file_name=f"教練查詢報表_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

def usage_page(me):
    st.header("銷課表")
    coaches=coach_options(); allowed=coaches if me["role"] in ("shared_coach","manager","admin") else {me["display_name"]:me["id"]}
    all_usage_purchase_keys=paged_rows(lambda: client().table("purchases").select("id,purchase_date,created_at")
        .order("purchase_date").order("created_at").order("id"))
    usage_purchase_code_map=_build_purchase_code_map(all_usage_purchase_keys)
    coach_date_limit={"min_value":date.today()} if me["role"]=="coach" else {}
    register_tab,cancel_tab,query_tab=st.tabs(["銷課登錄","上課預約取消","教練查詢"])
    with cancel_tab:
        st.markdown('<div style="font-size:1.5rem;font-weight:600;line-height:1.3;margin:0.25rem 0 1rem 0;">上課預約取消 <span style="font-size:0.75rem;font-weight:400;">（前一日及當日臨時請假者）</span></div>',unsafe_allow_html=True)
        with st.form("session_cancellation",clear_on_submit=True):
            c1,c2,c3=st.columns(3); cancel_date=c1.date_input("取消日期",date.today()); cancel_coach=c2.selectbox("教練",list(allowed)); cancel_count=c3.number_input("上課取消堂數",0,100,0)
            cancel_reason=st.text_input("取消原因"); add_cancel=st.form_submit_button("新增取消紀錄")
        if add_cancel:
            try:
                client().table("session_cancellations").insert({"cancel_date":str(cancel_date),"coach_id":allowed[cancel_coach],"cancelled_sessions":cancel_count,"reason":cancel_reason.strip() or None,"created_by":me["id"]}).execute()
                st.success("上課預約取消紀錄已新增。"); st.rerun()
            except Exception as exc: st.error(f"新增失敗：{exc}")
        cancellations=rows(client().table("session_cancellations").select("cancel_date,coach_id,cancelled_sessions,reason").order("cancel_date",desc=True).limit(100))
        coach_names={v:k for k,v in coaches.items()}
        cancellations=[x for x in cancellations if x.get("coach_id")==me["id"]] if me["role"]=="coach" else [x for x in cancellations if x.get("coach_id") in coach_names]
        for x in cancellations: x["coach_name"]=coach_names.get(x.pop("coach_id"),"未知")
        show_table(cancellations,["cancel_date","coach_name","cancelled_sessions","reason"])
    with register_tab:
        localize_usage_search_no_results()
        if me["role"]=="coach":
            owned_balances=rows(client().table("purchase_balances").select("member_id").eq("coach_id",me["id"]))
            owned_member_ids=list({x["member_id"] for x in owned_balances if x.get("member_id")})
            members=(rows(client().table("members").select("id,member_name").eq("active",True).in_("id",owned_member_ids).order("member_name"))
                if owned_member_ids else [])
        else:
            members=rows(client().table("members").select("id,member_name").eq("active",True).order("member_name"))
        if not members:
            st.info("請先建立課程購買紀錄。")
        else:
            member_map={x["member_name"]:x["id"] for x in members}
            member_name=st.selectbox("會員名稱",list(member_map),index=None,placeholder="輸入或選擇會員")
            if member_name:
                balances=rows(client().table("purchase_balances").select("*").eq("member_id",member_map[member_name]).gt("remaining_sessions",0))
                balances=[x for x in balances if x.get("coach_id")==me["id"]] if me["role"]=="coach" else [x for x in balances if x.get("coach_id") in set(coaches.values())]
                balance_purchase_ids=[x["purchase_id"] for x in balances]
                balance_purchase_dates=rows(client().table("purchases").select("id,purchase_date").in_("id",balance_purchase_ids)) if balance_purchase_ids else []
                balance_purchase_date_map={x["id"]:x.get("purchase_date") for x in balance_purchase_dates}
                for balance in balances: balance["purchase_date"]=balance_purchase_date_map.get(balance["purchase_id"])
                balances.sort(key=lambda x:str(x.get("purchase_date") or ""),reverse=True)
                show_table(balances,["purchase_date","course_name","coach_name","total_sessions","used_sessions","remaining_sessions","remaining_amount","expiry_date","status"])
                active=[x for x in balances if x["status"]=="active"]
                if not active:
                    st.warning("此會員沒有可扣課的有效課程。")
                else:
                    lookup={f'{usage_purchase_code_map.get(x["purchase_id"],x["purchase_id"])}｜{member_name}｜{x["course_name"]}｜{int(x["total_sessions"])} 堂｜{x["coach_name"]}｜剩餘 {int(x["remaining_sessions"])} 堂｜餘額 $ {float(x["remaining_amount"]):,.0f}':x for x in active}
                    label=st.selectbox("選擇課程",list(lookup),key=f"usage_course_{member_map[member_name]}")
                    selected=lookup[label]
                    with st.form(f'consume_{selected["purchase_id"]}'):
                        c1,c2=st.columns(2); usage_date=c1.date_input("銷課日期",date.today(),**coach_date_limit); c2.text_input("授課教練",value=selected["coach_name"],disabled=True)
                        note=st.text_area("備註",placeholder="可輸入本次銷課備註"); submit=st.form_submit_button("確認扣除 1 堂")
                    per=Decimal(str(selected["remaining_amount"])) if selected["remaining_sessions"]==1 else (Decimal(str(selected["total_amount"]))/selected["total_sessions"]).quantize(Decimal("0.01"))
                    st.caption(f"本次預計扣除：1 堂／$ {per:,.0f}；最後一堂會自動扣完剩餘金額。")
                    if submit:
                        try:
                            if me["role"]=="coach" and usage_date<date.today():
                                raise ValueError("教練只能填寫今天或未來的銷課日期")
                            client().rpc("consume_session",{"p_purchase_id":selected["purchase_id"],"p_usage_date":str(usage_date),"p_coach_id":selected["coach_id"],"p_note":note}).execute()
                            st.success("扣課完成。"); st.rerun()
                        except Exception as exc: st.error(f"扣課失敗：{exc}")
                    history=rows(client().table("session_usages").select("usage_date,coach_id,session_seq,deducted_amount,note").eq("purchase_id",selected["purchase_id"]).order("session_seq",desc=True))
                    names={v:k for k,v in coaches.items()}; history=[x for x in history if x.get("coach_id") in names]
                    for x in history: x["coach_name"]=names.get(x.pop("coach_id"),"未知")
                    st.subheader("扣課紀錄"); show_table(history,["usage_date","coach_name","session_seq","deducted_amount","note"])

        st.divider()
        st.subheader("近期銷課紀錄")
        recent_start=date.today()-timedelta(days=6)
        recent_end=date.today()
        recent_coach_id=me["id"] if me["role"]=="coach" else None
        recent_columns=["銷課日期","購買_ID","教練","會員名稱","課程名稱","堂次","備註"]
        def recent_usage_query():
            query=(client().table("session_usages").select("id,purchase_id,usage_date,coach_id,session_seq,note,created_at")
                .gte("usage_date",str(recent_start)).lte("usage_date",str(recent_end))
                .order("usage_date",desc=True).order("created_at",desc=True).order("id",desc=True))
            return query.eq("coach_id",recent_coach_id) if recent_coach_id else query.in_("coach_id",list(coaches.values()))
        recent_usages=paged_rows(recent_usage_query)
        recent_purchase_ids=list({x["purchase_id"] for x in recent_usages})
        recent_purchases=(rows(client().table("purchases").select("id,member_id,course_name").in_("id",recent_purchase_ids))
            if recent_purchase_ids else [])
        recent_purchase_map={x["id"]:x for x in recent_purchases}
        recent_member_ids=list({x["member_id"] for x in recent_purchases if x.get("member_id")})
        recent_members=(rows(client().table("members").select("id,member_name").in_("id",recent_member_ids))
            if recent_member_ids else [])
        recent_member_name_map={x["id"]:x["member_name"] for x in recent_members}
        recent_coach_name_map={coach_id:coach_name for coach_name,coach_id in coaches.items()}
        recent_rows=[]
        for usage in recent_usages:
            purchase=recent_purchase_map.get(usage["purchase_id"],{})
            recent_rows.append({
                "銷課日期":usage.get("usage_date"),
                "購買_ID":usage_purchase_code_map.get(usage["purchase_id"],usage["purchase_id"]),
                "教練":recent_coach_name_map.get(usage.get("coach_id"),"未知教練"),
                "會員名稱":recent_member_name_map.get(purchase.get("member_id"),""),
                "課程名稱":purchase.get("course_name") or "",
                "堂次":int(usage.get("session_seq") or 0),
                "備註":usage.get("note") or "",
            })
        recent_usage_df=pd.DataFrame(recent_rows,columns=recent_columns)
        st.caption(f"固定顯示 {recent_start} 至 {recent_end} 的銷課紀錄，並依日期由新至舊排列。")
        if recent_usage_df.empty:
            st.info("最近 7 天沒有銷課紀錄。")
        else:
            st.dataframe(recent_usage_df,hide_index=True,width="stretch")
    with query_tab:
        usage_query_tabs(me,purchase_code_map=usage_purchase_code_map)

def completed_purchase_ids(usages,purchase_map):
    """回傳在銷課明細中完成最後一堂的購買課程 ID；同一課程只計一次。"""
    return {usage["purchase_id"] for usage in usages
        if usage.get("purchase_id") in purchase_map
        and int(purchase_map[usage["purchase_id"]].get("total_sessions") or 0)>0
        and int(usage.get("session_seq") or 0)==int(purchase_map[usage["purchase_id"]].get("total_sessions") or 0)}

def dashboard_page(me):
    st.header("主管 Dashboard")
    if me["role"] not in ("manager","admin"): st.warning("此頁僅限主管與系統管理員使用。") ; return
    coaches=coach_options(); c1,c2,c3=st.columns(3)
    start=c1.date_input("開始日期",date.today().replace(day=1)); end=c2.date_input("結束日期",date.today())
    selected=c3.multiselect("教練",list(coaches),default=list(coaches))
    st.caption("※金額皆為含稅；續約率＝查詢期間續課購買筆數 ÷ 查詢期間課程結束筆數。")
    if start>end: st.error("開始日期不可晚於結束日期。") ; return
    ids=[coaches[x] for x in selected]
    cancellations=rows(client().table("session_cancellations").select("coach_id,cancelled_sessions,cancel_date").gte("cancel_date",str(start)).lte("cancel_date",str(end)))
    trials=rows(client().table("trial_items").select("coach_id,member_name,content,hours,entry_date").gte("entry_date",str(start)).lte("entry_date",str(end)))
    single_sales=rows(client().table("single_sales").select("coach_id,hours,entry_date").gte("entry_date",str(start)).lte("entry_date",str(end)))
    event_supports=rows(client().table("event_supports").select("coach_id,hours,deducted_hours,entry_date").gte("entry_date",str(start)).lte("entry_date",str(end)))
    project_entries=rows(client().table("project_entries").select("coach_id,item_hours,quantity,entry_date").gte("entry_date",str(start)).lte("entry_date",str(end)))
    purchases=rows(client().table("purchases").select("id,coach_id,purchase_kind,total_sessions,total_amount,purchase_date").gte("purchase_date",str(start)).lte("purchase_date",str(end)))
    def dashboard_usage_query():
        return (client().table("session_usages").select("id,purchase_id,coach_id,session_seq,deducted_amount,usage_date")
            .gte("usage_date",str(start)).lte("usage_date",str(end))
            .order("usage_date").order("id"))
    usages=paged_rows(dashboard_usage_query)
    dashboard_usage_purchase_ids=list({x["purchase_id"] for x in usages})
    completion_purchases=(rows(client().table("purchases").select("id,coach_id,total_sessions").in_("id",dashboard_usage_purchase_ids))
        if dashboard_usage_purchase_ids else [])
    completion_purchase_map={x["id"]:x for x in completion_purchases}
    completed_ids=completed_purchase_ids(usages,completion_purchase_map)
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
        trial_member_content={(str(x.get("member_name") or "").strip().casefold(),str(x.get("content") or "").strip().casefold())
            for x in trials if x["coach_id"]==cid and str(x.get("member_name") or "").strip() and str(x.get("content") or "").strip()}
        trial_count=len(trial_member_content)
        first_count=sum(1 for x in p if x["purchase_kind"]=="first")
        renewal_count=sum(1 for x in p if x["purchase_kind"]=="renewal")
        completed_count=sum(1 for purchase_id in completed_ids if completion_purchase_map[purchase_id].get("coach_id")==cid)
        received=sum(float(x["amount"]) for x in payments if payment_purchase_map.get(x["purchase_id"])==cid)
        used_sessions=len(u); used_amount=sum(float(x["deducted_amount"]) for x in u)
        execution_hours=(used_sessions+sum(float(x["hours"]) for x in trials if x["coach_id"]==cid)
            +sum(float(x["hours"]) for x in single_sales if x["coach_id"]==cid)
            +sum(float(x["hours"])-float(x.get("deducted_hours") or 0) for x in event_supports if x["coach_id"]==cid)
            +sum(float(x.get("item_hours") or 0)*float(x["quantity"]) for x in project_entries if x.get("coach_id")==cid))
        result.append({"教練":names[cid],"銷課堂數":used_sessions,"銷課金額":used_amount,
                       "上課取消率":cancelled/(used_sessions+cancelled) if used_sessions+cancelled else None,
                       "體驗人次":trial_count,"體驗成交率":first_count/trial_count if trial_count else None,
                       "續約率":renewal_count/completed_count if completed_count else None,"成交堂數":sessions,
                       "成交總金額":amount,"實際預收金額":received,
                       "平均每堂單價":amount/sessions if sessions else None,"總執行時數":execution_hours})
    df=pd.DataFrame(result)
    if df.empty: st.info("沒有可顯示的資料。") ; return
    totals=df[["成交堂數","成交總金額","實際預收金額","銷課堂數","銷課金額","總執行時數"]].sum()
    overall_trial_member_content={(str(x.get("member_name") or "").strip().casefold(),str(x.get("content") or "").strip().casefold())
        for x in trials if x["coach_id"] in ids and str(x.get("member_name") or "").strip() and str(x.get("content") or "").strip()}
    total_trial_count=len(overall_trial_member_content)
    total_first_count=len([x for x in purchases if x["coach_id"] in ids and x["purchase_kind"]=="first"])
    overall_trial_conversion=total_first_count/total_trial_count if total_trial_count else None
    total_renewals=len([x for x in purchases if x["coach_id"] in ids and x["purchase_kind"]=="renewal"])
    total_completed=len([purchase_id for purchase_id in completed_ids if completion_purchase_map[purchase_id].get("coach_id") in ids])
    overall_renewal=total_renewals/total_completed if total_completed else None
    total_cancelled=sum(x["cancelled_sessions"] for x in cancellations if x["coach_id"] in ids)
    overall_cancel_rate=total_cancelled/(totals["銷課堂數"]+total_cancelled) if totals["銷課堂數"]+total_cancelled else None
    average_unit=totals["成交總金額"]/totals["成交堂數"] if totals["成交堂數"] else None
    st.markdown("""
    <style>
    div[data-testid="stMetric"] {
        min-width: 0;
        padding: 0.75rem 0.7rem;
    }
    div[data-testid="stMetricLabel"] {
        min-height: 2rem;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: clamp(0.78rem, 1.1vw, 0.95rem);
        line-height: 1.25;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    div[data-testid="stMetricValue"] > div {
        font-size: clamp(1.05rem, 1.8vw, 1.65rem);
        line-height: 1.15;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    @media (max-width: 768px) {
        div[data-testid="stMetric"] { padding: 0.55rem 0.45rem; }
        div[data-testid="stMetricLabel"] p { font-size: 0.8rem; }
        div[data-testid="stMetricValue"] > div { font-size: 1.15rem; }
    }
    </style>
    """,unsafe_allow_html=True)
    dashboard_metrics=[
        ("銷課堂數",f'{totals["銷課堂數"]:,.0f}'),
        ("銷課金額",f'$ {totals["銷課金額"]:,.0f}'),
        ("上課取消率",f'{overall_cancel_rate:.1%}' if overall_cancel_rate is not None else "—"),
        ("體驗人次",f'{total_trial_count:,.0f}'),
        ("體驗成交率",f'{overall_trial_conversion:.1%}' if overall_trial_conversion is not None else "—"),
        ("續約率",f'{overall_renewal:.1%}' if overall_renewal is not None else "—"),
        ("成交堂數",f'{totals["成交堂數"]:,.0f}'),
        ("成交總金額",f'$ {totals["成交總金額"]:,.0f}'),
        ("實際預收金額",f'$ {totals["實際預收金額"]:,.0f}'),
        ("平均每堂單價",f'$ {average_unit:,.0f}' if average_unit is not None else "—"),
        ("總執行時數",f'{totals["總執行時數"]:,.2f} 小時'),
    ]
    for metric_start in range(0,len(dashboard_metrics),4):
        metric_group=dashboard_metrics[metric_start:metric_start+4]
        metric_columns=st.columns(len(metric_group))
        for metric_column,(metric_label,metric_value) in zip(metric_columns,metric_group):
            metric_column.metric(metric_label,metric_value)
    display_df=df.copy()
    display_df["上課取消率"]=display_df["上課取消率"]*100
    display_df["體驗成交率"]=display_df["體驗成交率"]*100
    display_df["續約率"]=display_df["續約率"]*100
    display_df=display_df[["教練","總執行時數","銷課堂數","銷課金額","上課取消率","體驗人次","體驗成交率","續約率","成交堂數","成交總金額","實際預收金額","平均每堂單價"]]
    st.dataframe(display_df,hide_index=True,use_container_width=True,column_config={"總執行時數":st.column_config.NumberColumn(format="%.2f 小時"),"上課取消率":st.column_config.NumberColumn(format="%.1f%%"),"體驗成交率":st.column_config.NumberColumn(format="%.1f%%"),"續約率":st.column_config.NumberColumn(format="%.1f%%"),"成交總金額":st.column_config.NumberColumn(format="$ %.0f"),"實際預收金額":st.column_config.NumberColumn(format="$ %.0f"),"銷課金額":st.column_config.NumberColumn(format="$ %.0f"),"平均每堂單價":st.column_config.NumberColumn(format="$ %.0f")})
    left,right=st.columns(2)
    count_metric=left.selectbox("數量指標",["成交堂數","銷課堂數","體驗人次"],key="dashboard_count_metric")
    amount_metric=right.selectbox("金額類型",["成交總金額","銷課金額"],key="dashboard_amount_metric")
    count_unit="人次" if count_metric=="體驗人次" else "堂數"
    left.plotly_chart(px.bar(df,x="教練",y=count_metric,title=f"{count_metric}比較（{start} 至 {end}）",labels={count_metric:count_unit}),use_container_width=True)
    right.plotly_chart(px.bar(df,x="教練",y=amount_metric,title=f"{amount_metric}比較（{start} 至 {end}）",labels={amount_metric:"$"}),use_container_width=True)
    st.plotly_chart(px.bar(df,x="教練",y="總執行時數",title=f"總執行時數比較（{start} 至 {end}）",labels={"總執行時數":"小時"}),use_container_width=True)

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
    courses=rows(admin.table("course_catalog").select("id,course_name,course_type,session_hours,active,created_at").order("course_name"))
    course_map={f'{x.get("course_type") or "未分類"}｜{x["course_name"]}':x for x in courses}
    add_tab,delete_tab,edit_tab=st.tabs(["新增","刪除","修改"])
    with add_tab:
        with st.form("add_course",clear_on_submit=True):
            c1,c2,c3=st.columns(3)
            course_name=c1.text_input("新增課程名稱").strip()
            course_type=c2.text_input("課程屬性").strip()
            course_hours=c3.number_input("每堂課時數",0.25,24.0,1.0,step=0.25,format="%.2f")
            add_course=st.form_submit_button("新增課程",type="primary")
        if add_course:
            if not course_name or not course_type: st.error("課程名稱與課程屬性不可空白。")
            else:
                try:
                    admin.table("course_catalog").insert({"course_name":course_name,"course_type":course_type,"session_hours":course_hours,"active":True}).execute()
                    st.success(f"已新增課程：{course_name}"); st.rerun()
                except Exception as exc: st.error(f"新增失敗，請確認課程名稱是否重複：{exc}")
    with delete_tab:
        if not courses: st.info("目前尚未建立課程名稱。")
        else:
            with st.form("delete_course"):
                selected_course=st.selectbox("選擇要刪除的課程",list(course_map))
                confirm_delete=st.checkbox("我確認刪除此課程名稱；既有會員購買紀錄仍會保留。")
                delete_course=st.form_submit_button("刪除課程名稱",type="primary")
            if delete_course:
                if not confirm_delete: st.error("請先勾選刪除確認。")
                else:
                    try:
                        admin.table("course_catalog").delete().eq("id",course_map[selected_course]["id"]).execute()
                        st.success(f"已刪除課程名稱：{selected_course}"); st.rerun()
                    except Exception as exc: st.error(f"刪除失敗：{exc}")
    with edit_tab:
        if not courses: st.info("目前尚未建立課程名稱。")
        else:
            course_display=[{**x,"課程屬性":x.get("course_type") or "","active":"啟用" if x.get("active",True) else "停用"} for x in courses]
            show_table(course_display,["課程屬性","course_name","session_hours","active","created_at"])
            selected_course=st.selectbox("選擇要修改的課程",list(course_map),key="course_edit_select")
            current=course_map[selected_course]
            with st.form("edit_course"):
                c1,c2,c3=st.columns(3)
                edited_name=c1.text_input("課程名稱",current["course_name"]).strip()
                edited_type=c2.text_input("課程屬性",current.get("course_type") or "").strip()
                edited_hours=c3.number_input("每堂課時數",0.25,24.0,float(current.get("session_hours") or 1),step=0.25,format="%.2f")
                edited_active=st.checkbox("啟用課程",value=bool(current.get("active",True)))
                save_course=st.form_submit_button("儲存修改",type="primary")
            if save_course:
                if not edited_name or not edited_type: st.error("課程名稱與課程屬性不可空白。")
                else:
                    try:
                        admin.table("course_catalog").update({"course_name":edited_name,"course_type":edited_type,"session_hours":edited_hours,"active":edited_active}).eq("id",current["id"]).execute()
                        st.success("課程資料已修改；既有購買紀錄仍保留原成交內容。"); st.rerun()
                    except Exception as exc: st.error(f"修改失敗，請確認課程名稱是否重複：{exc}")

def operation_item_admin_page(me, item_type, title):
    st.subheader(title)
    if me["role"] != "admin":
        st.warning("此功能僅限系統管理員使用。")
        return
    admin=admin_client()
    if admin is None:
        st.error("尚未設定 SUPABASE_SECRET_KEY。")
        return
    items=rows(admin.table("operation_item_catalog").select("id,item_name,detail_content,course_type,session_hours,default_amount,active,created_at").eq("item_type",item_type).order("item_name"))
    item_map={
        (f'{x["item_name"]}｜{x.get("detail_content") or ""}' if item_type=="trial" else x["item_name"]):x
        for x in items
    }
    add_tab,delete_tab,edit_tab=st.tabs(["新增","刪除","修改"])
    with add_tab:
        with st.form(f"add_operation_item_{item_type}",clear_on_submit=True):
            c1,c2,c3=st.columns(3)
            new_name=c1.text_input("新增項目名稱").strip()
            new_hours=c2.number_input("每堂課時數",0.25,24.0,1.0,step=0.25)
            new_amount=c3.number_input("預設金額（未稅）",0.0,1000000000.0,0.0,step=100.0,format="%.0f")
            new_detail=st.text_input("內容").strip() if item_type=="trial" else ""
            new_course_type=st.text_input("課程屬性").strip()
            add_item=st.form_submit_button("新增項目",type="primary")
        if add_item:
            if not new_name or not new_course_type or (item_type=="trial" and not new_detail): st.error("體驗項目、內容與課程屬性不可空白。" if item_type=="trial" else "項目名稱與課程屬性不可空白。")
            else:
                try:
                    admin.table("operation_item_catalog").insert({"item_type":item_type,"item_name":new_name,"detail_content":new_detail or None,"course_type":new_course_type or None,"session_hours":new_hours,"default_amount":new_amount,"active":True}).execute()
                    st.success(f"已新增：{new_name}"); st.rerun()
                except Exception as exc: st.error(f"新增失敗，請確認體驗項目與內容的組合是否重複：{exc}" if item_type=="trial" else f"新增失敗，請確認名稱是否重複：{exc}")
    with delete_tab:
        if not items: st.info("目前尚未建立項目。")
        else:
            with st.form(f"delete_operation_item_{item_type}"):
                delete_name=st.selectbox("選擇要刪除的項目",list(item_map),key=f"delete_select_{item_type}")
                confirm=st.checkbox("我確認刪除此下拉選項；既有歷史紀錄不會被刪除。")
                delete_item=st.form_submit_button("刪除項目",type="primary")
            if delete_item:
                if not confirm: st.error("請先勾選確認。")
                else:
                    try:
                        admin.table("operation_item_catalog").delete().eq("id",item_map[delete_name]["id"]).execute()
                        st.success(f"已刪除選項：{delete_name}"); st.rerun()
                    except Exception as exc: st.error(f"刪除失敗：{exc}")
    with edit_tab:
        if not items: st.info("目前尚未建立項目。")
        else:
            admin_columns=["item_name","detail_content","課程屬性","session_hours","default_amount","active","created_at"] if item_type=="trial" else ["item_name","課程屬性","session_hours","default_amount","created_at"]
            display_items=[{**x,"課程屬性":x.get("course_type") or "","active":"啟用" if x.get("active",True) else "停用"} for x in items]
            show_table(display_items,admin_columns)
            selected=st.selectbox("選擇要修改的項目",list(item_map),key=f"edit_select_{item_type}")
            current=item_map[selected]
            with st.form(f"edit_operation_item_{item_type}"):
                edited_name=st.text_input("修改後名稱",value=current["item_name"]).strip()
                edited_detail=st.text_input("修改後內容",value=current.get("detail_content") or "").strip() if item_type=="trial" else ""
                edited_course_type=st.text_input("修改後課程屬性",value=current.get("course_type") or "").strip()
                c1,c2=st.columns(2)
                edited_hours=c1.number_input("修改後每堂課時數",0.25,24.0,float(current.get("session_hours") or 1),step=0.25)
                edited_amount=c2.number_input("修改後預設金額（未稅）",0.0,1000000000.0,float(current.get("default_amount") or 0),step=100.0,format="%.0f")
                edited_active=st.checkbox("啟用體驗項目",value=bool(current.get("active",True))) if item_type=="trial" else True
                update_item=st.form_submit_button("儲存修改",type="primary")
            if update_item:
                if not edited_name or not edited_course_type or (item_type=="trial" and not edited_detail): st.error("體驗項目、內容與課程屬性不可空白。" if item_type=="trial" else "項目名稱與課程屬性不可空白。")
                else:
                    try:
                        payload={"item_name":edited_name,"detail_content":edited_detail or None,"course_type":edited_course_type or None,"session_hours":edited_hours,"default_amount":edited_amount}
                        if item_type=="trial": payload["active"]=edited_active
                        admin.table("operation_item_catalog").update(payload).eq("id",current["id"]).execute()
                        st.success("項目已修改。既有歷史紀錄仍保留原內容。"); st.rerun()
                    except Exception as exc: st.error(f"修改失敗，請確認體驗項目與內容的組合是否重複：{exc}" if item_type=="trial" else f"修改失敗，請確認名稱是否重複：{exc}")

def project_admin_page(me):
    st.subheader("專案管理")
    if me["role"]!="admin": st.warning("此功能僅限系統管理員使用。"); return
    admin=admin_client()
    try:
        projects=rows(admin.table("projects").select("id,project_name,funding_type,stored_date,stored_amount,active,created_at").order("project_name"))
    except Exception:
        st.error("專案主檔尚未建立，請先在 Supabase 執行 migration_project_v1_1_0.sql。")
        return

    project_tab,deposit_tab,item_tab=st.tabs(["專案設定","新增儲值／沖銷","操作項目管理"])
    with project_tab:
        st.caption("已儲值專案必須輸入實際儲值金額；未儲值專案採事後請款。")
        funding_label=st.radio("專案類型",["已儲值","未儲值"],horizontal=True,key="add_project_funding_type")
        with st.form("add_project_master",clear_on_submit=True,enter_to_submit=False):
            new_project_name=st.text_input("專案名稱").strip()
            if funding_label=="已儲值":
                c1,c2=st.columns(2)
                stored_date=c1.date_input("儲值日期",value=None,format="YYYY-MM-DD")
                stored_amount=c2.number_input("儲值金額",0.0,1000000000.0,0.0,step=100.0,format="%.0f")
            else:
                stored_date=None
                stored_amount=0.0
            add_project=st.form_submit_button("新增專案",type="primary",use_container_width=True)
        if add_project:
            if not new_project_name: st.error("專案名稱不可空白。")
            elif funding_label=="已儲值" and stored_date is None: st.error("已儲值專案必須填寫儲值日期。")
            elif funding_label=="已儲值" and stored_amount<=0: st.error("已儲值專案的儲值金額必須大於零。")
            else:
                try:
                    created_project=rows(admin.table("projects").insert({"project_name":new_project_name,
                        "funding_type":"stored" if funding_label=="已儲值" else "unfunded",
                        "stored_date":str(stored_date) if funding_label=="已儲值" else None,
                        "stored_amount":stored_amount if funding_label=="已儲值" else 0,
                        "active":True,"created_by":me["id"]}))
                    if not created_project:
                        raise ValueError("專案主檔建立後未取得新增資料")
                    if funding_label=="已儲值" and created_project:
                        try:
                            admin.table("project_deposits").insert({"project_id":created_project[0]["id"],
                                "deposit_date":str(stored_date),"amount":stored_amount,"transaction_type":"opening",
                                "note":"建立專案時的期初儲值","created_by":me["id"]}).execute()
                        except Exception as deposit_exc:
                            # 避免留下已儲值主檔已建立、期初儲值明細卻缺少的半完成資料。
                            admin.table("projects").delete().eq("id",created_project[0]["id"]).execute()
                            raise deposit_exc
                    st.success("專案已新增。"); st.rerun()
                except Exception as exc: st.error(f"新增失敗：{exc}")

        display_projects=[]
        for x in projects:
            display_projects.append({**x,"funding_type":"已儲值" if x["funding_type"]=="stored" else "未儲值"})
        show_table(display_projects,["project_name","funding_type","stored_date","stored_amount","active","created_at"])
        if projects:
            project_map={x["project_name"]:x for x in projects}
            edit_name=st.selectbox("選擇要修改的專案",list(project_map),key="project_master_edit_select")
            current=project_map[edit_name]
            edited_type_label=st.radio("修改後專案類型",["已儲值","未儲值"],
                index=0 if current["funding_type"]=="stored" else 1,horizontal=True,
                key=f'edit_project_funding_type_{current["id"]}')
            with st.form("edit_project_master",enter_to_submit=False):
                edited_name=st.text_input("修改後專案名稱",current["project_name"]).strip()
                if edited_type_label=="已儲值":
                    current_stored_date=date.fromisoformat(current["stored_date"]) if current.get("stored_date") else None
                    c1,c2=st.columns(2)
                    edited_stored_date=c1.date_input("修改後儲值日期",value=current_stored_date,format="YYYY-MM-DD")
                    edited_stored_amount=c2.number_input("修改後儲值金額",0.0,1000000000.0,
                        float(current.get("stored_amount") or 0),step=100.0,format="%.0f")
                else:
                    edited_stored_date=None
                    edited_stored_amount=0.0
                edited_active=st.checkbox("啟用專案",value=bool(current.get("active",True)))
                update_project=st.form_submit_button("儲存專案設定")
            if update_project:
                if not edited_name: st.error("專案名稱不可空白。")
                elif edited_type_label=="已儲值" and edited_stored_date is None: st.error("已儲值專案必須填寫儲值日期。")
                elif edited_type_label=="已儲值" and edited_stored_amount<=0: st.error("已儲值專案的儲值金額必須大於零。")
                else:
                    try:
                        funding_type="stored" if edited_type_label=="已儲值" else "unfunded"
                        amount=edited_stored_amount if funding_type=="stored" else 0
                        if funding_type=="stored":
                            used=rows(admin.table("project_funding_balances").select("used_amount").eq("project_id",current["id"]).limit(1))
                            used_amount=float(used[0]["used_amount"]) if used else 0
                            if amount<used_amount: raise ValueError(f"儲值金額不可小於已使用金額 $ {used_amount:,.0f}")
                            if current["funding_type"]=="stored" and amount!=float(current.get("stored_amount") or 0):
                                raise ValueError("既有儲值金額請至「新增儲值／沖銷」分頁處理，不可直接覆蓋。")
                        admin.table("projects").update({"project_name":edited_name,"funding_type":funding_type,
                            "stored_date":str(edited_stored_date) if funding_type=="stored" else None,
                            "stored_amount":amount,"active":edited_active,
                            "updated_at":pd.Timestamp.now(tz="UTC").isoformat()}).eq("id",current["id"]).execute()
                        admin.table("project_catalog").update({"project_name":edited_name}).eq("project_id",current["id"]).execute()
                        if current["funding_type"]=="unfunded" and funding_type=="stored":
                            admin.table("project_deposits").insert({"project_id":current["id"],
                                "deposit_date":str(edited_stored_date),"amount":amount,"transaction_type":"opening",
                                "note":"專案轉為已儲值","created_by":me["id"]}).execute()
                        st.success("專案設定已修改。"); st.rerun()
                    except Exception as exc: st.error(f"修改失敗：{exc}")

    with deposit_tab:
        stored_projects=[x for x in projects if x.get("funding_type")=="stored" and x.get("active")]
        if not stored_projects:
            st.info("目前沒有已啟用的儲值專案。")
        else:
            stored_project_map={x["project_name"]:x for x in stored_projects}
            st.caption("後續收到儲值款時新增一筆紀錄；輸入錯誤請使用沖銷，不直接刪除歷史。")
            with st.form("add_project_deposit_form",clear_on_submit=True,enter_to_submit=False):
                deposit_project_name=st.selectbox("專案名稱",list(stored_project_map),index=None,placeholder="請選擇專案")
                c1,c2=st.columns(2)
                deposit_date=c1.date_input("儲值日期",value=None,format="YYYY-MM-DD")
                deposit_amount=c2.number_input("儲值金額",0.0,1000000000.0,0.0,step=100.0,format="%.0f")
                deposit_note=st.text_input("備註").strip()
                add_deposit=st.form_submit_button("新增儲值紀錄",type="primary",use_container_width=True)
            if add_deposit:
                if not deposit_project_name: st.error("請選擇專案。")
                elif deposit_date is None: st.error("請填寫儲值日期。")
                elif deposit_amount<=0: st.error("儲值金額必須大於零。")
                else:
                    try:
                        admin.rpc("add_project_deposit",{"p_project_id":stored_project_map[deposit_project_name]["id"],
                            "p_deposit_date":str(deposit_date),"p_amount":deposit_amount,"p_note":deposit_note or None}).execute()
                        st.success("儲值紀錄已新增，累計儲值及剩餘金額已更新。"); st.rerun()
                    except Exception as exc: st.error(f"新增儲值失敗：{exc}")

            deposits=rows(admin.table("project_deposits").select("id,project_id,deposit_date,amount,transaction_type,reversed_deposit_id,note,created_at")
                .order("deposit_date",desc=True).order("created_at",desc=True).limit(500))
            project_names_by_id={x["id"]:x["project_name"] for x in projects}
            reversed_ids={x.get("reversed_deposit_id") for x in deposits if x.get("reversed_deposit_id")}
            deposit_display=[{"儲值日期":x["deposit_date"],"專案名稱":project_names_by_id.get(x["project_id"],"未知"),
                "類型":{"opening":"期初儲值","deposit":"後續儲值","reversal":"沖銷"}.get(x["transaction_type"],x["transaction_type"]),
                "金額":float(x["amount"]),"備註":x.get("note") or ""} for x in deposits]
            st.dataframe(pd.DataFrame(deposit_display),hide_index=True,use_container_width=True,
                column_config={"金額":st.column_config.NumberColumn(format="$ %.0f")})

            reversible=[x for x in deposits if float(x.get("amount") or 0)>0 and x["id"] not in reversed_ids]
            if reversible:
                reversal_map={f'{x["deposit_date"]}｜{project_names_by_id.get(x["project_id"],"未知")}｜$ {float(x["amount"]):,.0f}｜{x["id"][:8]}':x for x in reversible}
                with st.form("reverse_project_deposit_form",enter_to_submit=False):
                    reversal_label=st.selectbox("選擇要沖銷的儲值紀錄",list(reversal_map),index=None,placeholder="請選擇紀錄")
                    reversal_note=st.text_input("沖銷原因").strip()
                    reversal_confirm=st.checkbox("我確認建立等額負數沖銷紀錄；原始紀錄將保留。")
                    reverse_deposit=st.form_submit_button("建立沖銷紀錄")
                if reverse_deposit:
                    if not reversal_label: st.error("請選擇要沖銷的紀錄。")
                    elif not reversal_note: st.error("請填寫沖銷原因。")
                    elif not reversal_confirm: st.error("請先勾選確認。")
                    else:
                        try:
                            admin.rpc("reverse_project_deposit",{"p_deposit_id":reversal_map[reversal_label]["id"],"p_note":reversal_note}).execute()
                            st.success("沖銷紀錄已建立，原始儲值紀錄仍完整保留。"); st.rerun()
                        except Exception as exc: st.error(f"沖銷失敗：{exc}")

    with item_tab:
        active_projects=[x for x in projects if x.get("active")]
        project_map={x["project_name"]:x for x in active_projects}
        items=rows(admin.table("project_catalog").select("id,project_id,project_name,item_name,hours,price,created_at").order("project_name").order("item_name"))
        item_map={f'{x["project_name"]}｜{x["item_name"]}':x for x in items}
        add_item_tab,delete_item_tab,edit_item_tab=st.tabs(["新增","刪除","修改"])
        with add_item_tab:
            if not active_projects:
                st.info("請先新增並啟用專案。")
            else:
                with st.form("add_project_catalog",clear_on_submit=True,enter_to_submit=False):
                    c1,c2=st.columns(2)
                    selected_project_name=c1.selectbox("專案名稱",list(project_map),index=None,placeholder="請選擇專案")
                    item_name=c2.text_input("操作項目").strip()
                    c1,c2=st.columns(2)
                    hours=c1.number_input("時數",0.25,10000.0,1.0,step=0.25)
                    price=c2.number_input("價格",0.0,10000000.0,0.0,step=100.0,format="%.0f")
                    add_project_item=st.form_submit_button("新增專案操作項目",type="primary",use_container_width=True)
                if add_project_item:
                    if not selected_project_name or not item_name: st.error("專案名稱及操作項目不可空白。")
                    else:
                        try:
                            selected_project=project_map[selected_project_name]
                            admin.table("project_catalog").insert({"project_id":selected_project["id"],
                                "project_name":selected_project_name,"item_name":item_name,"hours":hours,"price":price}).execute()
                            st.success("專案操作項目已新增。"); st.rerun()
                        except Exception as exc: st.error(f"新增失敗，請確認專案與項目組合是否重複：{exc}")
        with delete_item_tab:
            if not items:
                st.info("目前尚未建立專案操作項目。")
            else:
                with st.form("delete_project_catalog",enter_to_submit=False):
                    delete_label=st.selectbox("選擇要刪除的專案操作項目",list(item_map),key="project_catalog_delete_select")
                    confirm=st.checkbox("我確認刪除此選項；已有歷史單據時系統會阻止刪除。")
                    delete_project_item=st.form_submit_button("刪除專案操作項目",type="primary")
                if delete_project_item:
                    if not confirm: st.error("請先勾選刪除確認。")
                    else:
                        try:
                            admin.table("project_catalog").delete().eq("id",item_map[delete_label]["id"]).execute()
                            st.success("專案操作項目已刪除。"); st.rerun()
                        except Exception as exc: st.error(f"刪除失敗；可能已有歷史單據使用此項目：{exc}")
        with edit_item_tab:
            if not items:
                st.info("目前尚未建立專案操作項目。")
            else:
                show_table(items,["project_name","item_name","hours","price","created_at"])
                selected=st.selectbox("選擇要修改的專案操作項目",list(item_map),key="project_catalog_edit_select")
                current_item=item_map[selected]
                with st.form("edit_project_catalog",enter_to_submit=False):
                    st.text_input("所屬專案",current_item["project_name"],disabled=True)
                    edited_item=st.text_input("修改後操作項目",current_item["item_name"]).strip()
                    c1,c2=st.columns(2)
                    edited_hours=c1.number_input("修改後時數",0.25,10000.0,float(current_item["hours"]),step=0.25)
                    edited_price=c2.number_input("修改後價格",0.0,10000000.0,float(current_item["price"]),step=100.0,format="%.0f")
                    update_project_item=st.form_submit_button("儲存操作項目修改",type="primary")
                if update_project_item:
                    if not edited_item: st.error("操作項目不可空白。")
                    else:
                        try:
                            admin.table("project_catalog").update({"item_name":edited_item,
                                "hours":edited_hours,"price":edited_price}).eq("id",current_item["id"]).execute()
                            st.success("操作項目已修改；歷史單據內容不受影響。"); st.rerun()
                        except Exception as exc: st.error(f"修改失敗：{exc}")

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

def _financial_backup_frames(table_data):
    """依現有財務報表規則，產生截至今日、不套用畫面篩選的完整財務工作表。"""
    today=str(date.today())
    profiles=table_data.get("profiles",[])
    members=table_data.get("members",[])
    purchases=[x for x in table_data.get("purchases",[]) if str(x.get("purchase_date") or "")<=today]
    payments=[x for x in table_data.get("purchase_payments",[]) if str(x.get("paid_date") or "")<=today]
    usages=[x for x in table_data.get("session_usages",[]) if str(x.get("usage_date") or "")<=today]
    projects=table_data.get("projects",[])
    project_entries=[x for x in table_data.get("project_entries",[]) if str(x.get("entry_date") or "")<=today]
    deposits=[x for x in table_data.get("project_deposits",[]) if str(x.get("deposit_date") or "")<=today]
    terminations=[x for x in table_data.get("course_terminations",[]) if str(x.get("termination_date") or "")<=today]
    member_name={x.get("id"):x.get("member_name") or "" for x in members}
    coach_name={x.get("id"):x.get("display_name") or x.get("username") or "" for x in profiles if x.get("role")=="coach"}
    purchase_map={x.get("id"):x for x in purchases}
    project_map={x.get("id"):x for x in projects}
    purchase_codes=_build_purchase_code_map(purchases)
    paid_map={}; used_map={}; used_sessions={}; paid_installments={}
    for x in payments:
        pid=x.get("purchase_id"); paid_map[pid]=paid_map.get(pid,0)+float(x.get("amount") or 0)
        if x.get("installment_no") is not None: paid_installments.setdefault(pid,set()).add(int(x["installment_no"]))
    for x in usages:
        pid=x.get("purchase_id"); used_map[pid]=used_map.get(pid,0)+float(x.get("deducted_amount") or 0)
        used_sessions[pid]=used_sessions.get(pid,0)+1
    status_labels={"active":"進行中","completed":"已完成","expired":"逾期中止","cancelled":"退費中止"}

    prepaid_rows=[]; outstanding_rows=[]
    for p in sorted(purchases,key=lambda x:str(x.get("purchase_date") or ""),reverse=True):
        pid=p.get("id"); total=float(p.get("total_amount") or 0); received=min(paid_map.get(pid,0),total)
        used=min(used_map.get(pid,0),total); total_sessions=int(p.get("total_sessions") or 0); session_count=used_sessions.get(pid,0)
        if received>=total: payment_status="付清"
        elif p.get("payment_plan")=="installment": payment_status=f'已付 {len(paid_installments.get(pid,set()))}/{int(p.get("installment_count") or 0)} 期'
        else: payment_status="未付清"
        prepaid_rows.append({"購買_ID":purchase_codes.get(pid,""),"成交日期":p.get("purchase_date"),"會員名稱":member_name.get(p.get("member_id"),""),
            "教練":coach_name.get(p.get("coach_id"),""),"課程名稱":p.get("course_name") or "","堂數":total_sessions,
            "分期期數／付清":payment_status,"成交金額":round(total),"實際預收金額":round(received)})
        raw_balance=max(received-used,0); balance=raw_balance if p.get("status")=="active" else 0
        outstanding_rows.append({"成交日期":p.get("purchase_date"),"購買_ID":purchase_codes.get(pid,""),"會員名稱":member_name.get(p.get("member_id"),""),
            "教練":coach_name.get(p.get("coach_id"),""),"課程名稱":p.get("course_name") or "","實際預收金額":round(received),
            "累計銷課金額":round(used),"實際預收剩餘金額":round(balance),"堂數":f"{session_count}／{total_sessions}",
            "有效期限":p.get("expiry_date"),"課程狀態":status_labels.get(p.get("status"),p.get("status") or "")})

    project_usage_rows=[]
    for x in sorted(project_entries,key=lambda r:str(r.get("entry_date") or ""),reverse=True):
        project=project_map.get(x.get("project_id"),{})
        project_usage_rows.append({"日期":x.get("entry_date"),"專案名稱":x.get("project_name") or project.get("project_name") or "",
            "使用者":x.get("person_name") or "","教練":coach_name.get(x.get("coach_id"),""),"操作項目":x.get("item_name") or "",
            "時數":float(x.get("item_hours") or 0)*float(x.get("quantity") or 0),"金額":round(float(x.get("line_amount") or 0)),
            "備註":x.get("note") or "","_type":project.get("funding_type")})
    deposit_rows=[{"儲值日期":x.get("deposit_date"),"專案名稱":project_map.get(x.get("project_id"),{}).get("project_name",""),
        "類型":{"opening":"期初儲值","deposit":"後續儲值","reversal":"沖銷"}.get(x.get("transaction_type"),x.get("transaction_type") or ""),
        "儲值金額":round(float(x.get("amount") or 0)),"備註":x.get("note") or ""} for x in sorted(deposits,key=lambda r:str(r.get("deposit_date") or ""),reverse=True)]
    used_project={}
    for x in project_entries: used_project[x.get("project_id")]=used_project.get(x.get("project_id"),0)+float(x.get("line_amount") or 0)
    funding_rows=[{"專案名稱":p.get("project_name") or "","儲值金額":round(float(p.get("stored_amount") or 0)),
        "已使用金額":round(used_project.get(p.get("id"),0)),"剩餘金額":round(float(p.get("stored_amount") or 0)-used_project.get(p.get("id"),0))}
        for p in projects if p.get("funding_type")=="stored"]

    def operation_summary(records):
        totals={}
        for x in records:
            course_type=str(x.get("course_type") or "未分類").strip() or "未分類"
            totals[course_type]=totals.get(course_type,0)+float(x.get("amount") or 0)
        return pd.DataFrame([{"課程屬性":k,"未稅金額":round(v)} for k,v in sorted(totals.items())],columns=["課程屬性","未稅金額"])

    referral_groups={}
    for p in purchases:
        referral=str(p.get("referral") or "").strip()
        if not referral: continue
        key=(referral,p.get("member_id")); item=referral_groups.setdefault(key,{"首購":0,"續約":0,"成交總金額":0})
        if p.get("purchase_kind")=="first": item["首購"]+=1
        elif p.get("purchase_kind")=="renewal": item["續約"]+=1
        item["成交總金額"]+=float(p.get("total_amount") or 0)
    referral_rows=[{"醫生轉介":k[0],"會員名稱":member_name.get(k[1],""),**v} for k,v in sorted(referral_groups.items())]
    course_type_map={str(x.get("course_name") or "").strip():str(x.get("course_type") or "未分類").strip() or "未分類" for x in table_data.get("course_catalog",[])}
    course_type_totals={}
    for p in purchases:
        ct=course_type_map.get(str(p.get("course_name") or "").strip(),"未分類"); course_type_totals.setdefault(ct,{"purchase":0,"usage":0})["purchase"]+=float(p.get("total_amount") or 0)
    for x in usages:
        p=purchase_map.get(x.get("purchase_id"),{}); ct=course_type_map.get(str(p.get("course_name") or "").strip(),"未分類")
        course_type_totals.setdefault(ct,{"purchase":0,"usage":0})["usage"]+=float(x.get("deducted_amount") or 0)
    course_type_rows=[{"課程屬性":k,"成交未稅金額":_tax_display_amount(v["purchase"],"未稅"),"銷課未稅金額":_tax_display_amount(v["usage"],"未稅")} for k,v in sorted(course_type_totals.items())]

    termination_rows=[]
    for x in sorted(terminations,key=lambda r:str(r.get("termination_date") or ""),reverse=True):
        p=purchase_map.get(x.get("purchase_id"),{}); expired=x.get("termination_type")=="expired"
        termination_rows.append({"日期":x.get("termination_date"),"購買_ID":purchase_codes.get(x.get("purchase_id"),""),"會員名稱":member_name.get(p.get("member_id"),""),
            "教練":coach_name.get(p.get("coach_id"),""),"課程名稱":p.get("course_name") or "","中止類型":"逾期中止" if expired else "退費中止",
            "退費前剩餘金額（未稅）":_tax_display_amount(x.get("remaining_amount"),"未稅"),"逾期入帳金額（未稅）":_tax_display_amount(x.get("recognized_amount"),"未稅") if expired else 0,
            "退費手續費（未稅）":_tax_display_amount(x.get("fee_amount"),"未稅") if not expired else 0,"實際退費金額（未稅）":_tax_display_amount(x.get("refund_amount"),"未稅") if not expired else 0,
            "中止原因":x.get("reason") or "","備註":x.get("note") or ""})

    usage_rows=[]
    for x in sorted(usages,key=lambda r:(str(r.get("usage_date") or ""),str(r.get("id") or "")),reverse=True):
        p=purchase_map.get(x.get("purchase_id"),{})
        usage_rows.append({"銷課日期":x.get("usage_date"),"購買_ID":purchase_codes.get(x.get("purchase_id"),""),"教練":coach_name.get(x.get("coach_id"),""),
            "會員名稱":member_name.get(p.get("member_id"),""),"課程名稱":p.get("course_name") or "","堂次":x.get("session_seq"),
            "銷課時數":float(p.get("session_hours") or 1),"銷課金額（未稅）":_tax_display_amount(x.get("deducted_amount"),"未稅"),"備註":x.get("note") or ""})

    coach_hours=[]; coach_revenues=[]
    trials=[x for x in table_data.get("trial_items",[]) if str(x.get("entry_date") or "")<=today]
    singles=[x for x in table_data.get("single_sales",[]) if str(x.get("entry_date") or "")<=today]
    events=[x for x in table_data.get("event_supports",[]) if str(x.get("entry_date") or "")<=today]
    months=sorted({str(x.get(field) or "")[:7] for records,field in [(trials,"entry_date"),(singles,"entry_date"),(events,"entry_date"),(project_entries,"entry_date"),(usages,"usage_date")] for x in records if x.get(field)})
    for report_month in months:
      for coach_id,name in sorted(coach_name.items(),key=lambda x:x[1]):
        month_trials=[x for x in trials if str(x.get("entry_date") or "").startswith(report_month)]
        month_singles=[x for x in singles if str(x.get("entry_date") or "").startswith(report_month)]
        month_events=[x for x in events if str(x.get("entry_date") or "").startswith(report_month)]
        month_projects=[x for x in project_entries if str(x.get("entry_date") or "").startswith(report_month)]
        coach_trials=[x for x in month_trials if x.get("coach_id")==coach_id]
        coach_singles=[x for x in month_singles if x.get("coach_id")==coach_id]
        trial_hours=sum(float(x.get("hours") or 0) for x in coach_trials if not is_magnetic_wave_operation(x))
        single_hours=sum(float(x.get("hours") or 0) for x in coach_singles if not is_magnetic_wave_operation(x))
        event_hours=sum(max(0,float(x.get("hours") or 0)-float(x.get("deducted_hours") or 0)) for x in month_events if x.get("coach_id")==coach_id)
        project_hours=sum(float(x.get("item_hours") or 0)*float(x.get("quantity") or 0) for x in month_projects if x.get("coach_id")==coach_id)
        coach_usages=[x for x in usages if x.get("coach_id")==coach_id and str(x.get("usage_date") or "").startswith(report_month)]
        normal_hours=sum(float(purchase_map.get(x.get("purchase_id"),{}).get("session_hours") or 1) for x in coach_usages if not is_magnetic_wave_course(purchase_map.get(x.get("purchase_id"),{}).get("course_name")))
        magnetic_hours=(sum(float(x.get("hours") or 0) for x in coach_trials if is_magnetic_wave_operation(x))
            +sum(float(x.get("hours") or 0) for x in coach_singles if is_magnetic_wave_operation(x))
            +sum(float(purchase_map.get(x.get("purchase_id"),{}).get("session_hours") or 1) for x in coach_usages if is_magnetic_wave_course(purchase_map.get(x.get("purchase_id"),{}).get("course_name"))))
        coach_hours.append({"報表月份":report_month,"教練":name,"體驗時數":trial_hours,"單堂時數":single_hours,"活動時數":event_hours,"專案時數":project_hours,
            "銷課時數":normal_hours,"可計執行時數":trial_hours+single_hours+event_hours+project_hours+normal_hours,"動磁波時數":magnetic_hours})
        trial_rev=sum(float(x.get("amount") or 0) for x in month_trials if x.get("coach_id")==coach_id); single_rev=sum(float(x.get("amount") or 0) for x in month_singles if x.get("coach_id")==coach_id)
        project_rev=sum(_tax_display_amount(x.get("line_amount"),"未稅") for x in month_projects if x.get("coach_id")==coach_id); usage_rev=sum(_tax_display_amount(x.get("deducted_amount"),"未稅") for x in coach_usages)
        coach_revenues.append({"報表月份":report_month,"教練":name,"體驗項目金額（未稅）":round(trial_rev),"單堂銷售金額（未稅）":round(single_rev),"專案（未稅）":round(project_rev),"銷課（未稅）":round(usage_rev),"金額總計（未稅）":round(trial_rev+single_rev+project_rev+usage_rev)})

    bonus_rules=sorted([x for x in table_data.get("bonus_rules",[]) if x.get("active")],key=lambda x:str(x.get("effective_from") or ""),reverse=True)
    talk_bonus_rows=[]
    for p in purchases:
        coach_id=p.get("coach_id")
        if coach_id not in coach_name: continue
        rule=_bonus_rule_for_date(bonus_rules,p.get("purchase_date")); eligible,reason=_bonus_eligibility(rule,p,"talk")
        untaxed=_tax_display_amount(p.get("total_amount"),"未稅"); rate=Decimal(str(rule.get("talk_rate") or 0)) if rule else Decimal("0")
        bonus=int((Decimal(untaxed)*rate).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) if eligible else 0
        talk_bonus_rows.append({"成交日期":p.get("purchase_date"),"購買_ID":purchase_codes.get(p.get("id"),""),"會員名稱":member_name.get(p.get("member_id"),""),
            "教練":coach_name.get(coach_id,""),"購買類型":"首次購買" if p.get("purchase_kind")=="first" else "續約" if p.get("purchase_kind")=="renewal" else p.get("purchase_kind") or "",
            "醫生轉介":p.get("referral") or "","成交未稅金額":untaxed,"談單率":float(rate)*100,"談單獎金":bonus,
            "適用規則":rule.get("rule_name") if rule else "","計算狀態":"已計算" if eligible else reason})
    talk_summary=[]
    for name in sorted(coach_name.values()):
        eligible_rows=[x for x in talk_bonus_rows if x["教練"]==name and x["計算狀態"]=="已計算"]
        talk_summary.append({"教練":name,"符合規則成交未稅金額總計":sum(x["成交未稅金額"] for x in eligible_rows),"談單獎金總計":sum(x["談單獎金"] for x in eligible_rows)})

    completed_usage={}
    for x in usages:
        p=purchase_map.get(x.get("purchase_id"),{}); total_sessions=int(p.get("total_sessions") or 0)
        if total_sessions and int(x.get("session_seq") or 0)==total_sessions: completed_usage[x.get("purchase_id")]=x
    completion_rows=[]
    completion_sources=[(pid,x,purchase_map.get(pid,{}),x.get("coach_id"),x.get("usage_date")) for pid,x in completed_usage.items()]
    completion_sources += [(x.get("purchase_id"),x,purchase_map.get(x.get("purchase_id"),{}),x.get("completion_bonus_coach_id"),x.get("termination_date")) for x in terminations
        if x.get("termination_type")=="expired" and x.get("completion_bonus_eligible")]
    for pid,source,p,coach_id,completed_date in completion_sources:
        if coach_id not in coach_name: continue
        rule=_bonus_rule_for_date(bonus_rules,completed_date); eligible,reason=_bonus_eligibility(rule,p,"completion")
        untaxed=_tax_display_amount(p.get("total_amount"),"未稅"); rate=Decimal(str(rule.get("completion_rate") or 0)) if rule else Decimal("0")
        bonus=int((Decimal(untaxed)*rate).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) if eligible else 0
        completion_rows.append({"課程完成日期":completed_date,"購買_ID":purchase_codes.get(pid,""),"會員名稱":member_name.get(p.get("member_id"),""),"教練":coach_name.get(coach_id,""),
            "課程名稱":p.get("course_name") or "","課程結束成交未稅金額":untaxed,"結單率":float(rate)*100,"結單獎金":bonus,
            "適用規則":rule.get("rule_name") if rule else "","計算狀態":"已計算" if eligible else reason})
    completion_summary=[]
    for name in sorted(coach_name.values()):
        eligible_rows=[x for x in completion_rows if x["教練"]==name and x["計算狀態"]=="已計算"]
        completion_summary.append({"教練":name,"符合規則課程結束成交未稅金額總計":sum(x["課程結束成交未稅金額"] for x in eligible_rows),"結單獎金總計":sum(x["結單獎金"] for x in eligible_rows)})

    visible=lambda rows_list:[{k:v for k,v in x.items() if not str(k).startswith("_")} for x in rows_list]
    return {
        "財務-成交預收總表":pd.DataFrame(prepaid_rows),"財務-預收餘額明細":pd.DataFrame(outstanding_rows),
        "財務-專案儲值狀況":pd.DataFrame(funding_rows),"財務-專案儲值明細":pd.DataFrame(deposit_rows),
        "財務-已儲值專案":pd.DataFrame(visible([x for x in project_usage_rows if x.get("_type")=="stored"])),
        "財務-未儲值專案":pd.DataFrame(visible([x for x in project_usage_rows if x.get("_type")=="unfunded"])),
        "財務-體驗項目報表":operation_summary(trials),"財務-單堂銷售報表":operation_summary(singles),
        "財務-醫生轉介":pd.DataFrame(referral_rows),"財務-課程屬性":pd.DataFrame(course_type_rows),
        "財務-銷課明細":pd.DataFrame(usage_rows),"財務-課程中止":pd.DataFrame(termination_rows),
        "財務-教練時數":pd.DataFrame(coach_hours),"財務-教練營收":pd.DataFrame(coach_revenues),
        "財務-教練談單獎金":pd.DataFrame(talk_bonus_rows),"財務-談單獎金總計":pd.DataFrame(talk_summary),
        "財務-教練結單獎金":pd.DataFrame(completion_rows),"財務-結單獎金總計":pd.DataFrame(completion_summary),
    }

def _full_system_backup_bytes(admin):
    table_sheets={
        "profiles":"帳號權限",
        "members":"會員名單",
        "course_catalog":"課程名稱",
        "operation_item_catalog":"營運項目",
        "daily_operations":"每日營運",
        "trial_items":"體驗項目",
        "single_sales":"單堂銷售",
        "event_supports":"活動支援",
        "session_cancellations":"上課預約取消",
        "purchases":"課程購買",
        "purchase_payments":"付款紀錄",
        "session_usages":"銷課紀錄",
        "projects":"專案主檔",
        "project_catalog":"專案操作項目",
        "project_entries":"專案執行紀錄",
        "project_deposits":"專案儲值紀錄",
        "project_wallet_transactions":"舊專案錢包交易",
        "project_receipt_transactions":"舊專案請款交易",
        "project_members":"舊專案會員",
        "bonus_rules":"獎金規則",
        "course_terminations":"課程中止",
    }
    backup_frames={}
    table_data={}
    summary_rows=[]
    errors=[]
    for table_name,sheet_name in table_sheets.items():
        try:
            order_column="member_id" if table_name=="project_members" else "id"
            table_rows=paged_rows(lambda table_name=table_name,order_column=order_column:
                admin.table(table_name).select("*").order(order_column))
            table_data[table_name]=table_rows
            backup_frames[sheet_name]=pd.DataFrame(table_rows)
            summary_rows.append({"資料表":table_name,"工作表":sheet_name,"資料筆數":len(table_rows),"備份狀態":"完成"})
        except Exception as exc:
            errors.append(f"{table_name}: {exc}")
    if errors:
        raise RuntimeError("完整備份失敗，未產生部分備份："+"；".join(errors))
    backup_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    financial_frames=_financial_backup_frames(table_data)
    backup_frames={"備份說明":pd.DataFrame([
        {"項目":"系統版本","內容":secret("APP_VERSION") or "v1.12.9"},
        {"項目":"備份時間","內容":backup_time},
        {"項目":"備份範圍","內容":"系統主要資料表完整資料及截至備份日的全部財務報表；保留UUID及關聯欄位"},
        {"項目":"不含內容","內容":"Supabase登入密碼、API金鑰及Streamlit Secrets"},
    ]),"資料筆數檢核":pd.DataFrame(summary_rows),**backup_frames,**financial_frames}
    return _excel_bytes(backup_frames)

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
    id_to_display_name={x["id"]:x["display_name"] for x in coach_profiles}
    coach_reference_to_id={}
    ambiguous_coach_references=set()
    for coach in coach_profiles:
        for reference in (coach.get("username"),coach.get("display_name")):
            key=str(reference or "").strip().casefold()
            if not key:
                continue
            if key in coach_reference_to_id and coach_reference_to_id[key]!=coach["id"]:
                ambiguous_coach_references.add(key)
            else:
                coach_reference_to_id[key]=coach["id"]
    members=rows(admin.table("members").select("id,member_name"))
    member_names={x["id"]:x["member_name"] for x in members}

    st.subheader("匯出資料報表")
    purchases=rows(admin.table("purchases").select("*").order("purchase_date"))
    purchase_code_map=_build_purchase_code_map(purchases)
    # 銷課匯入可使用對外顯示的「成交日期＋序號」，也保留資料庫 UUID 相容舊檔。
    purchase_reference_to_id={}
    for purchase in purchases:
        purchase_uuid=str(purchase["id"]).strip()
        purchase_code=str(purchase_code_map.get(purchase["id"],"")).strip()
        purchase_reference_to_id[purchase_uuid.casefold()]=purchase["id"]
        if purchase_code:
            purchase_reference_to_id[purchase_code.casefold()]=purchase["id"]
    payments=rows(admin.table("purchase_payments").select("purchase_id,amount,paid_date"))
    paid_map={}
    paid_date_map={}
    for x in payments:
        paid_map[x["purchase_id"]]=paid_map.get(x["purchase_id"],0)+float(x["amount"])
        paid_date_map[x["purchase_id"]]=max(str(x["paid_date"]),paid_date_map.get(x["purchase_id"],""))
    course_rows=[]
    for x in purchases:
        course_rows.append({"purchase_id":purchase_code_map[x["id"]],"member_name":member_names.get(x["member_id"],""),
            "purchase_kind":x["purchase_kind"],"coach_username":id_to_display_name.get(x["coach_id"],""),
            "course_name":x["course_name"],"total_sessions":x["total_sessions"],"session_hours":x.get("session_hours",1),
            "total_amount":x["total_amount"],"purchase_date":x["purchase_date"],"expiry_date":x["expiry_date"],
            "payment_plan":x["payment_plan"],"installment_count":x["installment_count"],
            "paid_amount":paid_map.get(x["id"],0),"paid_date":paid_date_map.get(x["id"],""),
            "referral":x.get("referral") or "","note":x.get("note") or ""})
    usages=rows(admin.table("session_usages").select("*").order("usage_date"))
    purchase_map={x["id"]:x for x in purchases}
    usage_rows=[]
    for x in usages:
        p=purchase_map.get(x["purchase_id"],{})
        usage_rows.append({"purchase_id":purchase_code_map.get(x["purchase_id"],""),"usage_id":x["id"],
            "member_name":member_names.get(p.get("member_id"),""),"course_name":p.get("course_name",""),
            "usage_date":x["usage_date"],"coach_username":id_to_display_name.get(x["coach_id"],""),
            "session_seq":x["session_seq"],"deducted_amount":x["deducted_amount"],"note":x.get("note") or ""})
    usage_export_columns=["purchase_id","usage_id","member_name","course_name","usage_date","coach_username","session_seq","deducted_amount","note"]
    trial_rows=rows(admin.table("trial_items").select("entry_date,member_name,content,detail_content,hours,amount,note,coach_id,created_at").order("entry_date"))
    single_sale_rows=rows(admin.table("single_sales").select("entry_date,member_name,content,hours,amount,note,coach_id,created_at").order("entry_date"))
    event_rows=rows(admin.table("event_supports").select("entry_date,content,hours,deducted_hours,deduction_reason,coach_id,created_at").order("entry_date"))
    for collection in (trial_rows,single_sale_rows,event_rows):
        for item in collection:
            item["coach_username"]=id_to_display_name.get(item.pop("coach_id"),"")
    report=_excel_bytes({"課程購買":pd.DataFrame(course_rows),"銷課表":pd.DataFrame(usage_rows,columns=usage_export_columns),
        "體驗項目":pd.DataFrame(trial_rows),"單堂銷售":pd.DataFrame(single_sale_rows),"活動支援":pd.DataFrame(event_rows)})
    st.download_button("下載資料匯出報表",report,file_name=f"健身房資料匯出報表_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

    st.divider(); st.subheader("匯入會員課程與銷課表")
    st.caption("請先下載範本。匯入會員課程時 purchase_id 可留空；匯入銷課表時 purchase_id 請填購買課程編號（成交日期＋序號，例如 20260817-001），亦相容舊版 UUID。")
    course_template=pd.DataFrame(columns=["purchase_id","member_name","purchase_kind","coach_username","course_name","total_sessions","session_hours","total_amount","purchase_date","expiry_date","payment_plan","installment_count","paid_amount","paid_date","referral","note"])
    usage_template=pd.DataFrame(columns=["purchase_id","usage_date","coach_username","note"])
    st.download_button("下載匯入範本",_excel_bytes({"會員課程":course_template,"銷課表":usage_template}),
        file_name="會員課程與銷課表_匯入範本.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    uploaded=st.file_uploader("選擇 Excel 檔案",type=["xlsx"],key="course_usage_import")
    if uploaded is not None:
        try:
            book=pd.ExcelFile(uploaded); errors=[]; clean_courses=[]; clean_usages=[]
            # Compare uploaded purchase IDs against both the current database
            # and earlier valid rows in the same workbook. Blank IDs remain
            # importable because they represent newly created purchases.
            database_purchase_ids=set(purchase_reference_to_id)
            seen_purchase_ids=set(database_purchase_ids)
            duplicate_purchase_rows=0
            duplicate_purchase_details=[]
            if not any(x in book.sheet_names for x in ("會員課程","銷課表")):
                errors.append("至少需要『會員課程』或『銷課表』工作表。")
            if "會員課程" in book.sheet_names:
                df=pd.read_excel(book,"會員課程").fillna("")
                required=set(course_template.columns)-{"purchase_id","referral","note"}
                if not required.issubset(df.columns): errors.append("會員課程欄位不完整。")
                else:
                    for i,row in df.iterrows():
                        try:
                            source_id=str(row.get("purchase_id","")).strip()
                            source_key=source_id.casefold()
                            if source_key and source_key in seen_purchase_ids:
                                duplicate_purchase_rows+=1
                                duplicate_purchase_details.append({
                                    "Excel列號":i+2,
                                    "purchase_id":source_id,
                                    "會員名稱":str(row.get("member_name","")).strip(),
                                    "課程名稱":str(row.get("course_name","")).strip(),
                                    "重複來源":"資料庫既有紀錄" if source_key in database_purchase_ids else "本次檔案內重複",
                                })
                                continue
                            username=str(row["coach_username"]).strip(); coach_key=username.casefold()
                            if coach_key in ambiguous_coach_references: raise ValueError("教練姓名重複，請改填登入帳號")
                            if coach_key not in coach_reference_to_id: raise ValueError("找不到教練帳號或姓名")
                            kind=str(row["purchase_kind"]).strip().lower(); plan=str(row["payment_plan"]).strip().lower()
                            if kind not in ("first","renewal"): raise ValueError("purchase_kind 必須為 first 或 renewal")
                            if plan not in ("full","installment"): raise ValueError("payment_plan 必須為 full 或 installment")
                            purchased=pd.to_datetime(row["purchase_date"]).date(); expiry=pd.to_datetime(row["expiry_date"]).date()
                            if expiry<purchased: raise ValueError("有效日期不可早於購買日期")
                            clean_courses.append({"source_id":source_id,"member_name":str(row["member_name"]).strip(),
                                "coach_id":coach_reference_to_id[coach_key],"purchase_kind":kind,"course_name":str(row["course_name"]).strip(),
                                "total_sessions":int(row["total_sessions"]),"session_hours":float(row["session_hours"]),"total_amount":float(row["total_amount"]),
                                "purchase_date":str(purchased),"expiry_date":str(expiry),"payment_plan":plan,"installment_count":int(row["installment_count"]),
                                "paid_amount":float(row["paid_amount"] or 0),"paid_date":str(pd.to_datetime(row["paid_date"]).date()) if row["paid_date"] else str(purchased),
                                "referral":str(row.get("referral","")).strip() or None,"note":str(row.get("note","")).strip() or None})
                            if source_key:
                                seen_purchase_ids.add(source_key)
                        except Exception as exc: errors.append(f"會員課程第 {i+2} 列：{exc}")
            if "銷課表" in book.sheet_names:
                df=pd.read_excel(book,"銷課表").fillna("")
                if not set(usage_template.columns).issubset(df.columns): errors.append("銷課表欄位不完整。")
                else:
                    workbook_purchase_references={
                        str(item.get("source_id") or "").strip().casefold()
                        for item in clean_courses
                        if str(item.get("source_id") or "").strip()
                    }
                    for i,row in df.iterrows():
                        try:
                            purchase_reference=str(row["purchase_id"]).strip()
                            purchase_key=purchase_reference.casefold()
                            if not purchase_key:
                                raise ValueError("purchase_id 不可空白")
                            if purchase_key not in purchase_reference_to_id and purchase_key not in workbook_purchase_references:
                                raise ValueError(f"找不到 purchase_id：{purchase_reference}")
                            username=str(row["coach_username"]).strip(); coach_key=username.casefold()
                            if coach_key in ambiguous_coach_references: raise ValueError("教練姓名重複，請改填登入帳號")
                            if coach_key not in coach_reference_to_id: raise ValueError("找不到教練帳號或姓名")
                            clean_usages.append({"source_row":i+2,"purchase_reference":purchase_reference,"purchase_key":purchase_key,
                                "usage_date":str(pd.to_datetime(row["usage_date"]).date()),"coach_id":coach_reference_to_id[coach_key],
                                "note":str(row["note"]).strip() or None,"skip_existing":False})
                        except Exception as exc: errors.append(f"銷課表第 {i+2} 列：{exc}")
            # 以購買課程、日期、教練及備註做多重集合比對；重新上傳同一份檔案時，
            # 只略過資料庫中已存在的相同筆數，避免先前部分成功後再次重複扣課。
            existing_usage_counts={}
            for usage in usages:
                signature=(str(usage.get("purchase_id") or ""),str(usage.get("usage_date") or ""),
                    str(usage.get("coach_id") or ""),str(usage.get("note") or "").strip().casefold())
                existing_usage_counts[signature]=existing_usage_counts.get(signature,0)+1
            skipped_existing_usages=0
            duplicate_usage_details=[]
            for item in clean_usages:
                existing_purchase_id=purchase_reference_to_id.get(item["purchase_key"])
                if not existing_purchase_id:
                    continue
                signature=(str(existing_purchase_id),item["usage_date"],str(item["coach_id"]),str(item.get("note") or "").strip().casefold())
                if existing_usage_counts.get(signature,0)>0:
                    item["skip_existing"]=True
                    existing_usage_counts[signature]-=1
                    skipped_existing_usages+=1
                    duplicate_usage_details.append({
                        "Excel列號":item["source_row"],
                        "purchase_id":item["purchase_reference"],
                        "銷課日期":item["usage_date"],
                        "教練":id_to_display_name.get(item["coach_id"],""),
                        "備註":item.get("note") or "",
                        "重複來源":"資料庫既有銷課紀錄",
                    })

            # 匯入前先核對每筆購買課程的可用堂數，避免執行到一半才因堂數不足中止。
            required_usage_counts={}
            for item in clean_usages:
                if not item["skip_existing"]:
                    required_usage_counts[item["purchase_key"]]=required_usage_counts.get(item["purchase_key"],0)+1
            purchase_by_id={str(x["id"]):x for x in purchases}
            existing_used_counts={}
            for usage in usages:
                pid=str(usage.get("purchase_id") or "")
                existing_used_counts[pid]=existing_used_counts.get(pid,0)+1
            new_course_by_key={str(x.get("source_id") or "").strip().casefold():x for x in clean_courses if str(x.get("source_id") or "").strip()}
            for purchase_key,required_count in required_usage_counts.items():
                existing_purchase_id=purchase_reference_to_id.get(purchase_key)
                if existing_purchase_id:
                    purchase=purchase_by_id.get(str(existing_purchase_id),{})
                    available=max(int(purchase.get("total_sessions") or 0)-existing_used_counts.get(str(existing_purchase_id),0),0)
                    if purchase.get("status")!="active" and required_count>0:
                        errors.append(f"銷課表 purchase_id {purchase_key}：課程狀態不是有效，尚有 {required_count} 筆未匯入")
                    elif required_count>available:
                        errors.append(f"銷課表 purchase_id {purchase_key}：需匯入 {required_count} 筆，但剩餘堂數只有 {available}")
                else:
                    new_course=new_course_by_key.get(purchase_key)
                    available=int(new_course.get("total_sessions") or 0) if new_course else 0
                    if required_count>available:
                        errors.append(f"銷課表 purchase_id {purchase_key}：需匯入 {required_count} 筆，但新課程堂數只有 {available}")
            if errors: st.error("匯入檢查未通過：\n- "+"\n- ".join(errors[:30]))
            else:
                pending_usage_count=len(clean_usages)-skipped_existing_usages
                st.success(f"檢查通過：會員課程 {len(clean_courses)} 筆、待匯入銷課 {pending_usage_count} 筆。")
                if duplicate_purchase_rows:
                    st.info(f"已略過 purchase_id 重複的會員課程資料 {duplicate_purchase_rows} 筆（包含資料庫既有資料及本次檔案內重複資料）。")
                    st.dataframe(pd.DataFrame(duplicate_purchase_details),hide_index=True,use_container_width=True)
                if skipped_existing_usages:
                    st.info(f"已辨識銷課表中 {skipped_existing_usages} 筆資料庫既有紀錄，確認匯入時將自動略過，避免重複扣課。")
                    st.dataframe(pd.DataFrame(duplicate_usage_details),hide_index=True,use_container_width=True)
                if duplicate_purchase_details or duplicate_usage_details:
                    duplicate_report={}
                    if duplicate_purchase_details:
                        duplicate_report["會員課程重複"] = pd.DataFrame(duplicate_purchase_details)
                    if duplicate_usage_details:
                        duplicate_report["銷課表重複"] = pd.DataFrame(duplicate_usage_details)
                    st.download_button("下載重複資料明細",_excel_bytes(duplicate_report),
                        file_name=f"匯入重複資料明細_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                if st.button("確認匯入",type="primary"):
                    for item in clean_courses:
                        existing=rows(admin.table("members").select("id").eq("member_name",item["member_name"]))
                        member_id=existing[0]["id"] if existing else rows(admin.table("members").insert({"member_name":item["member_name"],"created_by":me["id"]}))[0]["id"]
                        payload={k:v for k,v in item.items() if k not in ("source_id","member_name","paid_amount","paid_date")}
                        payload.update({"member_id":member_id,"created_by":me["id"]})
                        created=rows(admin.table("purchases").insert(payload))[0]
                        source_key=str(item.get("source_id") or "").strip().casefold()
                        if source_key:
                            purchase_reference_to_id[source_key]=created["id"]
                        if item["paid_amount"]>0: admin.table("purchase_payments").insert({"purchase_id":created["id"],"installment_no":1,"amount":item["paid_amount"],"paid_date":item["paid_date"],"created_by":me["id"]}).execute()
                    imported_usage_count=0
                    failed_usage_rows=[]
                    for item in clean_usages:
                        if item["skip_existing"]:
                            continue
                        try:
                            purchase_id=purchase_reference_to_id.get(item["purchase_key"])
                            if not purchase_id: raise ValueError(f'找不到 purchase_id：{item["purchase_reference"]}')
                            client().rpc("consume_session",{"p_purchase_id":purchase_id,"p_usage_date":item["usage_date"],"p_coach_id":item["coach_id"],"p_note":item["note"]}).execute()
                            imported_usage_count+=1
                        except Exception as exc:
                            failed_usage_rows.append({"Excel列號":item["source_row"],"purchase_id":item["purchase_reference"],
                                "銷課日期":item["usage_date"],"失敗原因":str(exc)})
                    if failed_usage_rows:
                        st.error(f"匯入完成但有失敗資料：成功 {imported_usage_count} 筆、已略過 {skipped_existing_usages} 筆、失敗 {len(failed_usage_rows)} 筆。")
                        st.dataframe(pd.DataFrame(failed_usage_rows),hide_index=True,use_container_width=True)
                    else:
                        st.success(f"資料匯入完成：成功 {imported_usage_count} 筆、已略過既有紀錄 {skipped_existing_usages} 筆、失敗 0 筆。")
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
    coach_map={x["display_name"]:x["id"] for x in coaches if x["role"]=="coach"}
    id_name={x["id"]:x["display_name"] for x in coaches}
    data_types=["體驗項目","單堂銷售","活動支援","專案","上課預約取消","課程購買","銷課表"]
    st.markdown("#### 資料類型")
    data_type=st.segmented_control(
        "資料類型分頁",data_types,default="體驗項目",
        key="manage_data_type",label_visibility="collapsed"
    )
    if data_type is None:
        data_type="體驗項目"
    st.divider()
    if data_type=="上課預約取消":
        with st.expander("新增上課預約取消",expanded=False):
            with st.form("admin_add_session_cancellation",clear_on_submit=True):
                c1,c2,c3=st.columns(3)
                new_cancel_date=c1.date_input("取消日期",date.today(),key="admin_cancel_date")
                new_cancel_coach=c2.selectbox("教練",list(coach_map),key="admin_cancel_coach")
                new_cancel_count=c3.number_input("上課取消堂數",0,100,0,key="admin_cancel_count")
                new_cancel_reason=st.text_input("取消原因",key="admin_cancel_reason")
                add_cancel=st.form_submit_button("新增紀錄")
            if add_cancel:
                try:
                    admin.table("session_cancellations").insert({"cancel_date":str(new_cancel_date),"coach_id":coach_map[new_cancel_coach],"cancelled_sessions":new_cancel_count,"reason":new_cancel_reason.strip() or None,"created_by":me["id"]}).execute()
                    st.success("上課預約取消紀錄已新增。"); st.rerun()
                except Exception as exc: st.error(f"新增失敗：{exc}")
        records=rows(admin.table("session_cancellations").select("*").order("cancel_date",desc=True).limit(500))
        labels={f'{x["cancel_date"]}｜{id_name.get(x["coach_id"],"未知")}｜取消 {x["cancelled_sessions"]} 堂｜{x["id"][:8]}':x for x in records}
    elif data_type=="體驗項目":
        records=rows(admin.table("trial_items").select("*").order("entry_date",desc=True).limit(500))
        labels={f'{x["entry_date"]}｜{x.get("member_name") or "未填姓名"}｜{id_name.get(x["coach_id"],"未知")}｜{x["id"][:8]}':x for x in records}
    elif data_type=="單堂銷售":
        records=rows(admin.table("single_sales").select("*").order("entry_date",desc=True).limit(500))
        labels={f'{x["entry_date"]}｜{x.get("member_name") or "未填姓名"}｜{x["content"]}｜{id_name.get(x["coach_id"],"未知")}｜{x["id"][:8]}':x for x in records}
    elif data_type=="活動支援":
        records=rows(admin.table("event_supports").select("*").order("entry_date",desc=True).limit(500))
        labels={f'{x["entry_date"]}｜{x["content"]}｜{id_name.get(x["coach_id"],"未知")}｜{x["id"][:8]}':x for x in records}
    elif data_type=="專案":
        records=rows(admin.table("project_entries").select("*").order("entry_date",desc=True).limit(500))
        labels={f'{x["entry_date"]}｜{x["project_name"]}｜{x["person_name"]}｜{id_name.get(x.get("coach_id"),"未知")}｜{x["id"][:8]}':x for x in records}
    elif data_type=="課程購買":
        records=rows(admin.table("purchase_balances").select("*").order("expiry_date",desc=True).limit(500))
        record_purchase_ids=[x["purchase_id"] for x in records]
        purchase_details=rows(admin.table("purchases").select("id,purchase_date,purchase_kind,coach_id").in_("id",record_purchase_ids)) if record_purchase_ids else []
        purchase_detail_map={x["id"]:x for x in purchase_details}
        all_purchase_keys=rows(admin.table("purchases").select("id,purchase_date,created_at"))
        record_purchase_code_map=_build_purchase_code_map(all_purchase_keys)
        for item in records:
            detail=purchase_detail_map.get(item["purchase_id"],{})
            item["purchase_date"]=detail.get("purchase_date")
            item["purchase_kind"]=detail.get("purchase_kind")
            item["coach_id"]=detail.get("coach_id") or item.get("coach_id")
            item["purchase_code"]=record_purchase_code_map.get(item["purchase_id"],item["purchase_id"])
        records.sort(key=lambda x:str(x.get("purchase_date") or ""),reverse=True)
        labels={f'{x.get("purchase_date") or "日期不明"}｜{x["purchase_code"]}｜{x["member_name"]}｜{x["course_name"]}｜{x["total_sessions"]} 堂｜{id_name.get(x.get("coach_id"),x.get("coach_name") or "未知教練")}':x for x in records}
    else:
        # 銷課紀錄可能超過 Data API 單次回傳上限；分批讀取後再套用會員、教練及 purchase_id 篩選。
        # 使用穩定的多欄排序，避免相同日期資料在分頁邊界重複或遺漏。
        records=[]
        usage_page_size=1000
        usage_offset=0
        while True:
            usage_page=rows(admin.table("session_usages").select("*")
                .order("usage_date",desc=True).order("created_at",desc=True).order("id",desc=True)
                .range(usage_offset,usage_offset+usage_page_size-1))
            records.extend(usage_page)
            if len(usage_page)<usage_page_size:
                break
            usage_offset+=usage_page_size
        usage_purchase_ids=list({x["purchase_id"] for x in records})
        usage_purchases=rows(admin.table("purchase_balances").select("purchase_id,member_name,course_name").in_("purchase_id",usage_purchase_ids)) if usage_purchase_ids else []
        usage_member_map={x["purchase_id"]:x.get("member_name") or "會員不明" for x in usage_purchases}
        usage_course_map={x["purchase_id"]:x.get("course_name") or "課程不明" for x in usage_purchases}
        all_usage_purchase_keys=rows(admin.table("purchases").select("id,purchase_date,created_at"))
        usage_purchase_code_map=_build_purchase_code_map(all_usage_purchase_keys)
        labels={f'purchase_id：{usage_purchase_code_map.get(x["purchase_id"],x["purchase_id"])}｜{usage_member_map.get(x["purchase_id"],"會員不明")}｜{id_name.get(x["coach_id"],"未知教練")}｜{usage_course_map.get(x["purchase_id"],"課程不明")}｜第{x["session_seq"]}堂｜銷課日期：{x["usage_date"]}':x for x in records}

    st.markdown("#### 搜尋紀錄")
    search_col1,search_col2=st.columns(2)
    coach_search=search_col1.selectbox(
        "教練搜尋",["全部教練"]+list(coach_map),
        key=f"record_coach_search_{data_type}"
    )
    member_search=""
    if data_type in ("體驗項目","單堂銷售","課程購買","銷課表"):
        member_search=search_col2.text_input(
            "會員名稱搜尋",placeholder="可輸入完整或部分姓名",
            key=f"record_member_search_{data_type}"
        ).strip().casefold()
    else:
        search_col2.caption("此資料類型沒有會員名稱欄位。")
    purchase_id_search=""
    if data_type in ("課程購買","銷課表"):
        purchase_id_search=st.text_input(
            "purchase_id 搜尋",placeholder="可輸入完整或部分購買編號",
            key=f"record_purchase_id_search_{data_type}"
        ).strip().casefold()

    selected_search_coach_id=coach_map.get(coach_search)
    filtered_labels={}
    for label,item in labels.items():
        if selected_search_coach_id and item.get("coach_id")!=selected_search_coach_id:
            continue
        if member_search:
            if data_type in ("體驗項目","單堂銷售"):
                item_member=str(item.get("member_name") or "")
            elif data_type=="課程購買":
                item_member=str(item.get("member_name") or "")
            else:
                item_member=str(usage_member_map.get(item.get("purchase_id"),""))
            if member_search not in item_member.strip().casefold():
                continue
        if purchase_id_search:
            if data_type=="課程購買":
                purchase_code=str(item.get("purchase_code") or "")
            elif data_type=="銷課表":
                purchase_code=str(usage_purchase_code_map.get(item.get("purchase_id"),item.get("purchase_id") or ""))
            else:
                purchase_code=""
            searchable_purchase_ids=f'{purchase_code} {item.get("purchase_id") or ""}'.casefold()
            if purchase_id_search not in searchable_purchase_ids:
                continue
        filtered_labels[label]=item
    labels=filtered_labels
    st.caption(f"符合搜尋條件：{len(labels)} 筆")
    if not labels: st.info("目前沒有可管理的資料。"); return
    selected=st.selectbox("選擇紀錄",list(labels)); record=labels[selected]
    record_coach_map=dict(coach_map)
    if data_type in ("體驗項目","單堂銷售","活動支援","專案","上課預約取消","課程購買","銷課表") and record.get("coach_id") not in record_coach_map.values():
        historical_name=id_name.get(record.get("coach_id"),f'歷史帳號 {str(record.get("coach_id",""))[:8]}')
        record_coach_map[f'{historical_name}（歷史資料）']=record.get("coach_id")
    coach_names=list(record_coach_map)
    current_coach_index=list(record_coach_map.values()).index(record.get("coach_id")) if record.get("coach_id") in record_coach_map.values() else 0
    with st.form("record_edit"):
        if data_type=="上課預約取消":
            c1,c2,c3=st.columns(3)
            d=c1.date_input("取消日期",pd.to_datetime(record["cancel_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index); cancelled_sessions=c3.number_input("上課取消堂數",0,100,int(record["cancelled_sessions"]))
            reason=st.text_input("取消原因",record.get("reason") or "")
        elif data_type=="體驗項目":
            c1,c2=st.columns(2); d=c1.date_input("日期",pd.to_datetime(record["entry_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index)
            member_name=st.text_input("體驗會員姓名",record.get("member_name") or ""); content=st.text_input("體驗項目",record["content"]); detail_content=st.text_input("內容",record.get("detail_content") or ""); hours=st.number_input("時數",0.25,24.0,float(record["hours"]),step=0.25); amount=st.number_input("金額（未稅）",0.0,1000000000.0,float(record.get("amount") or 0),step=100.0,format="%.0f"); note=st.text_input("備註",record.get("note") or "")
        elif data_type=="單堂銷售":
            c1,c2=st.columns(2); d=c1.date_input("日期",pd.to_datetime(record["entry_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index)
            member_name=st.text_input("單堂銷售會員姓名",record.get("member_name") or ""); content=st.text_input("銷售內容",record["content"]); hours=st.number_input("時數",0.25,24.0,float(record["hours"]),step=0.25); amount=st.number_input("金額（未稅）",0.0,1000000000.0,float(record.get("amount") or 0),step=100.0,format="%.0f"); note=st.text_input("備註",record.get("note") or "")
        elif data_type=="活動支援":
            c1,c2=st.columns(2); d=c1.date_input("日期",pd.to_datetime(record["entry_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index)
            content=st.text_input("活動內容",record["content"])
            c1,c2=st.columns(2); hours=c1.number_input("時數",0.25,24.0,float(record["hours"]),step=0.25); deducted_hours=c2.number_input("應扣除時間",0.0,24.0,float(record["deducted_hours"]),step=0.25)
            deduction_reason=st.text_input("扣除原因",record.get("deduction_reason") or "")
        elif data_type=="專案":
            project_catalog=rows(admin.table("project_catalog").select("id,project_name,item_name,hours,price").order("project_name").order("item_name"))
            project_catalog_map={f'{x["project_name"]}｜{x["item_name"]}｜{float(x["hours"]):g} 小時｜$ {float(x["price"]):,.0f}':x for x in project_catalog}
            project_catalog_labels=list(project_catalog_map)
            current_catalog_index=next((i for i,label in enumerate(project_catalog_labels) if project_catalog_map[label]["id"]==record.get("project_catalog_id")),0)
            selected_project_item=st.selectbox("專案及操作項目",project_catalog_labels,index=current_catalog_index)
            c1,c2=st.columns(2); d=c1.date_input("日期",pd.to_datetime(record["entry_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index)
            person_name=st.text_input("使用者",record.get("person_name") or "")
            c1,c2=st.columns(2)
            quantity=c1.number_input("數量",0.01,100000.0,float(record["quantity"]),step=1.0)
            total_price=c2.number_input("價格",0.0,1000000000.0,float(record["quantity"])*float(record["unit_price"]),step=100.0,format="%.0f",help="此處為本筆總價。")
            project_note=st.text_input("備註",record.get("note") or "")
        elif data_type=="課程購買":
            c1,c2=st.columns(2)
            purchase_kind_label=c1.selectbox("購買類型",["首次購買","續課"],index=0 if record.get("purchase_kind")=="first" else 1)
            coach=c2.selectbox("指導教練",coach_names,index=current_coach_index)
            c1,c2,c3=st.columns(3); sessions=c1.number_input("課程堂數",1,999,int(record["total_sessions"])); amount=c2.number_input("成交總金額",0.0,10000000.0,float(record["total_amount"]),step=100.0,format="%.0f"); expiry=c3.date_input("有效期限",pd.to_datetime(record["expiry_date"]).date())
            referral=st.text_input("醫生轉介",record.get("referral") or "")
            note=st.text_area("備註",record.get("note") or "")
        else:
            c1,c2=st.columns(2); d=c1.date_input("銷課日期",pd.to_datetime(record["usage_date"]).date()); coach=c2.selectbox("教練",coach_names,index=current_coach_index); note=st.text_area("備註",record.get("note") or "")
        update=st.form_submit_button("儲存修改")
    if update:
        try:
            if data_type=="上課預約取消":
                admin.table("session_cancellations").update({"cancel_date":str(d),"coach_id":record_coach_map[coach],"cancelled_sessions":cancelled_sessions,"reason":reason.strip() or None}).eq("id",record["id"]).execute()
            elif data_type=="體驗項目":
                if not member_name.strip() or not content.strip(): raise ValueError("體驗會員姓名及體驗項目不可空白")
                admin.table("trial_items").update({"entry_date":str(d),"coach_id":record_coach_map[coach],"member_name":member_name.strip(),"content":content.strip(),"detail_content":detail_content.strip() or None,"hours":hours,"amount":amount,"note":note.strip() or None}).eq("id",record["id"]).execute()
            elif data_type=="單堂銷售":
                if not member_name.strip() or not content.strip(): raise ValueError("單堂銷售會員姓名及銷售內容不可空白")
                admin.table("single_sales").update({"entry_date":str(d),"coach_id":record_coach_map[coach],"member_name":member_name.strip(),"content":content.strip(),"hours":hours,"amount":amount,"note":note.strip() or None}).eq("id",record["id"]).execute()
            elif data_type=="活動支援":
                if not content.strip(): raise ValueError("活動內容不可空白")
                if deducted_hours>hours: raise ValueError("應扣除時間不可大於活動時數")
                if deducted_hours>0 and not deduction_reason.strip(): raise ValueError("有扣除時間時必須填寫扣除原因")
                admin.table("event_supports").update({"entry_date":str(d),"coach_id":record_coach_map[coach],"content":content.strip(),"hours":hours,"deducted_hours":deducted_hours,"deduction_reason":deduction_reason.strip() or None}).eq("id",record["id"]).execute()
            elif data_type=="專案":
                if not person_name.strip(): raise ValueError("使用者不可空白")
                catalog_item=project_catalog_map[selected_project_item]
                admin.table("project_entries").update({"entry_date":str(d),"project_catalog_id":catalog_item["id"],
                    "project_name":catalog_item["project_name"],"person_name":person_name.strip(),"coach_id":record_coach_map[coach],
                    "item_name":catalog_item["item_name"],"item_hours":float(catalog_item["hours"]),"quantity":quantity,
                    "unit_price":total_price/quantity,"line_amount":total_price,"note":project_note.strip() or None}).eq("id",record["id"]).execute()
            elif data_type=="課程購買": admin.table("purchases").update({"purchase_kind":"first" if purchase_kind_label=="首次購買" else "renewal","coach_id":record_coach_map[coach],"total_sessions":sessions,"total_amount":amount,"expiry_date":str(expiry),"referral":referral.strip() or None,"note":note.strip() or None}).eq("id",record["purchase_id"]).execute()
            else:
                old_date,old_coach=record["usage_date"],record["coach_id"]
                admin.table("session_usages").update({"usage_date":str(d),"coach_id":record_coach_map[coach],"note":note or None}).eq("id",record["id"]).execute()
                _sync_daily_classes(admin,old_date,old_coach); _sync_daily_classes(admin,d,record_coach_map[coach])
            st.success("資料已修改。"); st.rerun()
        except Exception as exc: st.error(f"修改失敗：{exc}")
    st.divider()
    st.subheader("刪除資料")
    delete_mode=st.radio(
        "刪除方式",["刪除目前選擇的單筆","選擇多筆刪除"],horizontal=True,
        key=f"delete_mode_{data_type}"
    )
    if delete_mode=="刪除目前選擇的單筆":
        delete_records=[record]
        st.info(f"目前選擇：{selected}")
    else:
        select_all=st.checkbox("選取目前查詢結果的全部資料",key=f"delete_all_{data_type}")
        delete_labels=list(labels) if select_all else st.multiselect(
            "選擇要刪除的紀錄",list(labels),key=f"delete_records_{data_type}"
        )
        delete_records=[labels[label] for label in delete_labels]
    if delete_records:
        st.warning(f"即將刪除 {len(delete_records)} 筆「{data_type}」資料。")
    purchase_delete_blockers=[]
    if data_type=="課程購買" and delete_records:
        selected_purchase_ids=list({item["purchase_id"] for item in delete_records})
        existing_usage_rows=rows(admin.table("session_usages").select("purchase_id").in_("purchase_id",selected_purchase_ids))
        usage_count_by_purchase={}
        for usage in existing_usage_rows:
            purchase_id=usage["purchase_id"]
            usage_count_by_purchase[purchase_id]=usage_count_by_purchase.get(purchase_id,0)+1
        purchase_delete_blockers=[{
            "購買_ID":item.get("purchase_code") or item["purchase_id"],
            "會員名稱":item.get("member_name") or "",
            "課程名稱":item.get("course_name") or "",
            "銷課紀錄筆數":usage_count_by_purchase[item["purchase_id"]],
        } for item in delete_records if usage_count_by_purchase.get(item["purchase_id"],0)>0]
        if purchase_delete_blockers:
            st.error("以下課程已有銷課紀錄，不能刪除課程購買。請先至「銷課表」刪除該課程的全部銷課紀錄，再回來刪除課程購買。")
            st.dataframe(pd.DataFrame(purchase_delete_blockers),hide_index=True,width="stretch")
    with st.form("record_delete"):
        confirm=st.checkbox(f"我確認刪除已選取的 {len(delete_records)} 筆資料；此操作無法復原。",disabled=bool(purchase_delete_blockers))
        delete=st.form_submit_button("刪除目前紀錄" if len(delete_records)==1 else "刪除選取紀錄",type="primary",disabled=bool(purchase_delete_blockers))
    if delete:
        if not delete_records: st.error("請先選擇至少一筆要刪除的資料。")
        elif not confirm: st.error("請先勾選刪除確認。")
        else:
            try:
                record_ids=[item["id"] for item in delete_records if item.get("id")]
                if data_type=="上課預約取消": admin.table("session_cancellations").delete().in_("id",record_ids).execute()
                elif data_type=="體驗項目": admin.table("trial_items").delete().in_("id",record_ids).execute()
                elif data_type=="單堂銷售": admin.table("single_sales").delete().in_("id",record_ids).execute()
                elif data_type=="活動支援": admin.table("event_supports").delete().in_("id",record_ids).execute()
                elif data_type=="專案": admin.table("project_entries").delete().in_("id",record_ids).execute()
                elif data_type=="課程購買":
                    purchase_ids=list({item["purchase_id"] for item in delete_records})
                    usage_still_exists=rows(admin.table("session_usages").select("purchase_id").in_("purchase_id",purchase_ids).limit(1))
                    if usage_still_exists:
                        raise ValueError("課程已有銷課紀錄；請先刪除該課程的全部銷課紀錄，確認為零筆後才能刪除課程購買。")
                    admin.table("purchases").delete().in_("id",purchase_ids).execute()
                else:
                    affected={(item["usage_date"],item["coach_id"]) for item in delete_records}
                    affected_purchase_ids=list({item["purchase_id"] for item in delete_records})
                    admin.table("session_usages").delete().in_("id",record_ids).execute()
                    if affected_purchase_ids:
                        admin.table("purchases").update({"status":"active"}).in_("id",affected_purchase_ids).eq("status","completed").execute()
                    for usage_date,coach_id in affected: _sync_daily_classes(admin,usage_date,coach_id)
                st.success(f"已刪除 {len(delete_records)} 筆資料。"); st.rerun()
            except Exception as exc: st.error(f"刪除失敗：{exc}")

def bonus_rule_admin_page(me):
    st.subheader("獎金規則管理")
    if me["role"]!="admin": st.warning("此功能僅限系統管理員使用。"); return
    admin=admin_client()
    if admin is None: st.error("尚未設定 SUPABASE_SECRET_KEY。"); return
    try:
        rules=rows(admin.table("bonus_rules").select("*").order("effective_from",desc=True))
    except Exception:
        st.error("尚未建立獎金規則資料表，請先執行 migration_bonus_rules_v1_8_0.sql。")
        return
    display_rows=[]
    for rule in rules:
        display_rows.append({"規則名稱":rule["rule_name"],"生效日期":rule["effective_from"],"結束日期":rule.get("effective_to") or "無期限",
            "談單獎金率":float(rule["talk_rate"])*100,"結單獎金率":float(rule["completion_rate"])*100,
            "轉介首購談單":"計算" if rule["referral_first_talk_eligible"] else "不計",
            "轉介首購結單":"計算" if rule["referral_first_completion_eligible"] else "不計",
            "轉介續約談單":"計算" if rule["referral_renewal_talk_eligible"] else "不計",
            "轉介續約結單":"計算" if rule["referral_renewal_completion_eligible"] else "不計",
            "狀態":"啟用" if rule["active"] else "停用","備註":rule.get("note") or ""})
    if display_rows:
        st.dataframe(pd.DataFrame(display_rows),hide_index=True,use_container_width=True,
            column_config={"談單獎金率":st.column_config.NumberColumn(format="%.2f%%"),"結單獎金率":st.column_config.NumberColumn(format="%.2f%%")})
    add_tab,end_tab=st.tabs(["新增規則","結束現行規則"])
    with add_tab:
        st.caption("新增規則前，請先將日期重疊的現行規則設定結束日期；歷史規則的比例不會被覆蓋。")
        with st.form("add_bonus_rule",clear_on_submit=True):
            rule_name=st.text_input("規則名稱").strip()
            c1,c2,c3=st.columns(3)
            effective_from=c1.date_input("生效日期",date.today())
            no_end=c2.checkbox("無結束日期",value=True)
            effective_to=c3.date_input("結束日期",date.today())
            c1,c2=st.columns(2)
            talk_rate_percent=c1.number_input("談單獎金率（%）",0.0,100.0,3.0,step=0.1,format="%.2f")
            completion_rate_percent=c2.number_input("結單獎金率（%）",0.0,100.0,4.0,step=0.1,format="%.2f")
            st.markdown("**醫生轉介適用條件**")
            c1,c2=st.columns(2)
            referral_first_talk=c1.checkbox("轉介首購計算談單獎金",value=False)
            referral_first_completion=c2.checkbox("轉介首購計算結單獎金",value=False)
            c1,c2=st.columns(2)
            referral_renewal_talk=c1.checkbox("轉介續約計算談單獎金",value=True)
            referral_renewal_completion=c2.checkbox("轉介續約計算結單獎金",value=True)
            note=st.text_area("備註")
            create_rule=st.form_submit_button("新增獎金規則",type="primary",use_container_width=True)
        if create_rule:
            end_value=None if no_end else effective_to
            if not rule_name: st.error("規則名稱不可空白。")
            elif end_value and end_value<effective_from: st.error("結束日期不可早於生效日期。")
            else:
                try:
                    admin.table("bonus_rules").insert({"rule_name":rule_name,"effective_from":str(effective_from),
                        "effective_to":str(end_value) if end_value else None,"talk_rate":talk_rate_percent/100,
                        "completion_rate":completion_rate_percent/100,"referral_first_talk_eligible":referral_first_talk,
                        "referral_first_completion_eligible":referral_first_completion,"referral_renewal_talk_eligible":referral_renewal_talk,
                        "referral_renewal_completion_eligible":referral_renewal_completion,"note":note.strip() or None,"created_by":me["id"]}).execute()
                    st.success("獎金規則已新增。"); st.rerun()
                except Exception as exc: st.error(f"新增失敗，請確認規則期間是否重疊：{exc}")
    with end_tab:
        active_rules=[x for x in rules if x.get("active",True)]
        if not active_rules: st.info("目前沒有可設定結束日期的規則。")
        else:
            active_map={f'{x["rule_name"]}｜{x["effective_from"]} 至 {x.get("effective_to") or "無期限"}':x for x in active_rules}
            selected_rule_name=st.selectbox("選擇規則",list(active_map),key="end_bonus_rule_select")
            selected_rule=active_map[selected_rule_name]
            with st.form("end_bonus_rule"):
                close_date=st.date_input("新的結束日期",date.today())
                confirm_close=st.checkbox("我確認只調整結束日期，不修改此規則既有比例。")
                close_rule=st.form_submit_button("設定規則結束日期",type="primary")
            if close_rule:
                if not confirm_close: st.error("請先勾選確認。")
                elif close_date<pd.to_datetime(selected_rule["effective_from"]).date(): st.error("結束日期不可早於生效日期。")
                else:
                    try:
                        admin.table("bonus_rules").update({"effective_to":str(close_date)}).eq("id",selected_rule["id"]).execute()
                        st.success("規則結束日期已更新。"); st.rerun()
                    except Exception as exc: st.error(f"更新失敗：{exc}")

def session_usage_export_query(me):
    st.subheader("銷課查詢")
    admin=admin_client()
    profiles=rows(admin.table("profiles").select("id,display_name,role").order("display_name"))
    operational_profiles=[x for x in profiles if x.get("role") in ("coach","manager")]
    coach_options_map={x["display_name"]:x["id"] for x in operational_profiles}
    coach_name_map={x["id"]:x["display_name"] for x in operational_profiles}
    c1,c2,c3=st.columns(3)
    start=c1.date_input("開始日期",date.today().replace(day=1),key="admin_usage_query_start")
    end=c2.date_input("結束日期",date.today(),key="admin_usage_query_end")
    selected_coach=c3.selectbox("教練",["全部教練"]+list(coach_options_map),key="admin_usage_query_coach")
    member_keyword=st.text_input("會員名稱",placeholder="可輸入完整或部分姓名",key="admin_usage_query_member").strip().casefold()
    if start>end:
        st.error("開始日期不可晚於結束日期。")
        return

    # 銷課紀錄可能超過 Data API 單次回傳上限；依日期與教練條件分批讀取完整結果。
    # 穩定排序可避免相同銷課日期的資料在分頁邊界重複或遺漏。
    usage_rows=[]
    usage_page_size=1000
    usage_offset=0
    while True:
        query=(admin.table("session_usages").select("id,purchase_id,usage_date,coach_id,created_at")
            .gte("usage_date",str(start)).lte("usage_date",str(end))
            .order("usage_date",desc=True).order("created_at",desc=True).order("id",desc=True)
            .range(usage_offset,usage_offset+usage_page_size-1))
        if selected_coach!="全部教練":
            query=query.eq("coach_id",coach_options_map[selected_coach])
        usage_page=rows(query)
        usage_rows.extend(usage_page)
        if len(usage_page)<usage_page_size:
            break
        usage_offset+=usage_page_size
    purchase_ids=list({x["purchase_id"] for x in usage_rows})
    purchases=rows(admin.table("purchases").select("id,member_id,course_name,session_hours").in_("id",purchase_ids)) if purchase_ids else []
    purchase_map={x["id"]:x for x in purchases}
    member_ids=list({x["member_id"] for x in purchases})
    members=rows(admin.table("members").select("id,member_name").in_("id",member_ids)) if member_ids else []
    member_name_map={x["id"]:x["member_name"] for x in members}
    display_rows=[]
    for usage in usage_rows:
        purchase=purchase_map.get(usage["purchase_id"],{})
        member_name=member_name_map.get(purchase.get("member_id"),"")
        if member_keyword and member_keyword not in member_name.strip().casefold():
            continue
        display_rows.append({
            "日期":usage["usage_date"],
            "教練名稱":coach_name_map.get(usage["coach_id"],"未知教練"),
            "會員名稱":member_name,
            "課程名稱":purchase.get("course_name", ""),
            "時數":float(purchase.get("session_hours") or 1),
        })
    result_df=pd.DataFrame(display_rows,columns=["日期","教練名稱","會員名稱","課程名稱","時數"])
    st.caption(f"符合搜尋條件：{len(result_df)} 筆")
    st.dataframe(result_df,hide_index=True,use_container_width=True,
        column_config={"時數":st.column_config.NumberColumn(format="%.2f")})
    st.download_button("下載銷課查詢結果",_excel_bytes({"銷課查詢":result_df}),
        file_name=f"銷課查詢_{start}_{end}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)

def data_management_page(me):
    st.header("資料管理")
    if me["role"]!="admin": st.warning("此頁僅限系統管理員使用。"); return
    if admin_client() is None: st.error("尚未設定 SUPABASE_SECRET_KEY。"); return
    tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs(["課程名稱管理","體驗項目管理","單堂銷售管理","專案管理","獎金規則管理","資料匯入／匯出","修改／刪除"])
    with tab1: course_admin_page(me)
    with tab2: operation_item_admin_page(me,"trial","體驗項目管理")
    with tab3: operation_item_admin_page(me,"single_sale","單堂銷售管理")
    with tab4: project_admin_page(me)
    with tab5: bonus_rule_admin_page(me)
    with tab6:
        io_tab,usage_query_tab,backup_tab=st.tabs(["資料匯入／匯出","銷課查詢","一鍵下載備份"])
        with io_tab: member_course_io_page(me)
        with usage_query_tab: session_usage_export_query(me)
        with backup_tab:
            st.subheader("一鍵下載完整資料及財務報表備份")
            st.caption("同一份 Excel 包含系統主要原始資料表，以及截至下載當日、不套用畫面篩選的全部財務報表工作表；不包含登入密碼、API金鑰及Streamlit Secrets。")
            backup_admin=admin_client()
            backup_stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button("下載完整資料及財務報表備份",data=lambda: _full_system_backup_bytes(backup_admin),
                file_name=f"秀傳運醫營運系統_完整資料及財務報表備份_{backup_stamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",type="primary",width="stretch",on_click="ignore")
    with tab7: record_admin_page(me)

def _tax_display_amount(amount, tax_mode):
    value=Decimal(str(amount or 0))
    if tax_mode=="未稅": value=value/Decimal("1.05")
    return int(value.quantize(Decimal("1"),rounding=ROUND_HALF_UP))

def _bonus_rule_for_date(rules,event_date):
    target=pd.to_datetime(event_date).date()
    applicable=[]
    for rule in rules:
        if not rule.get("active",True): continue
        start=pd.to_datetime(rule["effective_from"]).date()
        end=pd.to_datetime(rule["effective_to"]).date() if rule.get("effective_to") else None
        if start<=target and (end is None or target<=end): applicable.append(rule)
    return max(applicable,key=lambda x:str(x["effective_from"])) if applicable else None

def _bonus_eligibility(rule,purchase,bonus_kind):
    if not rule: return False,"查無適用的獎金規則"
    if not str(purchase.get("referral") or "").strip(): return True,"符合規則"
    purchase_kind=purchase.get("purchase_kind")
    if purchase_kind=="first": field=f"referral_first_{bonus_kind}_eligible"
    elif purchase_kind=="renewal": field=f"referral_renewal_{bonus_kind}_eligible"
    else: return True,"符合規則"
    if rule.get(field,False): return True,"符合規則"
    return False,"醫生轉介首購不計獎金" if purchase_kind=="first" else "醫生轉介續約不計獎金"

def _build_purchase_code_map(purchases):
    ordered=sorted(purchases,key=lambda x:(str(x.get("purchase_date") or ""),str(x.get("created_at") or ""),str(x["id"])))
    daily_sequences={}
    code_map={}
    for purchase in ordered:
        purchase_date_key=str(purchase.get("purchase_date") or "")
        daily_sequences[purchase_date_key]=daily_sequences.get(purchase_date_key,0)+1
        code_map[purchase["id"]]=f'{purchase_date_key.replace("-","")}-{daily_sequences[purchase_date_key]:03d}'
    return code_map

def course_termination_report_page(me):
    st.subheader("課程中止")
    st.caption("逾期餘額轉列入帳；退費金額為剩餘金額扣除選擇性 20% 手續費。兩者均不計入銷課及執行時數。")
    coaches=coach_options(); coach_name_map={v:k for k,v in coaches.items()}
    members=rows(client().table("members").select("id,member_name"))
    member_name_map={x["id"]:x["member_name"] for x in members}
    all_purchase_keys=rows(client().table("purchases").select("id,purchase_date,created_at").order("purchase_date"))
    purchase_code_map=_build_purchase_code_map(all_purchase_keys)

    try:
        balances=rows(client().table("purchase_balances").select("*").eq("status","active").gt("remaining_sessions",0).order("expiry_date"))
        active_ids=[x["purchase_id"] for x in balances]
        active_purchases=rows(client().table("purchases").select("id,purchase_date,member_id,course_name,total_amount,total_sessions").in_("id",active_ids)) if active_ids else []
        active_purchase_map={x["id"]:x for x in active_purchases}
        option_map={}
        for balance in balances:
            purchase=active_purchase_map.get(balance["purchase_id"],{})
            label=(f'{purchase.get("purchase_date") or "日期不明"}｜{purchase_code_map.get(balance["purchase_id"],"")}｜'
                   f'{balance["member_name"]}｜{balance["course_name"]}｜剩 {balance["remaining_sessions"]} 堂｜$ {float(balance["remaining_amount"]):,.0f}')
            option_map[label]=balance
    except Exception:
        st.error("尚未建立課程中止資料表，請先執行 migration_course_termination_v1_11_0.sql。")
        return

    entry_tab,history_tab=st.tabs(["新增中止","中止紀錄"])
    with entry_tab:
        if not option_map:
            st.info("目前沒有可中止的有效課程。")
        else:
            selected_label=st.selectbox("選擇會員課程",list(option_map),index=None,placeholder="請選擇尚有餘額的課程")
            selected=option_map.get(selected_label) if selected_label else None
            termination_label=st.segmented_control("中止類型",["逾期中止","退費中止"],default="逾期中止")
            charge_fee=False; bonus_eligible=False; bonus_coach=None
            if termination_label=="退費中止":
                charge_fee=st.checkbox("收取剩餘金額 20% 手續費",value=True)
            else:
                bonus_eligible=st.checkbox("計算結單獎金",value=False)
                if bonus_eligible:
                    bonus_coach=st.selectbox("結單獎金歸屬教練",list(coaches),index=None,placeholder="請選擇教練")
            if selected:
                remaining=Decimal(str(selected.get("remaining_amount") or 0))
                fee=(remaining*Decimal("0.20")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP) if charge_fee else Decimal("0")
                refund=remaining-fee if termination_label=="退費中止" else Decimal("0")
                c1,c2,c3=st.columns(3)
                c1.metric("退費前剩餘金額",f"$ {remaining:,.0f}")
                c2.metric("手續費",f"$ {fee:,.0f}")
                c3.metric("實際退費金額",f"$ {refund:,.0f}")
            with st.form("course_termination_form",enter_to_submit=False):
                termination_date=st.date_input("中止日期",date.today())
                reason=st.text_input("中止原因")
                note=st.text_area("備註")
                submitted=st.form_submit_button("確認中止課程",type="primary",width="stretch")
            if submitted:
                errors=[]
                if selected is None: errors.append("請選擇會員課程")
                if not reason.strip(): errors.append("請填寫中止原因")
                if termination_label=="逾期中止" and bonus_eligible and bonus_coach is None: errors.append("請選擇結單獎金歸屬教練")
                if errors:
                    st.error("；".join(errors)+"。")
                else:
                    try:
                        client().rpc("terminate_course",{
                            "p_purchase_id":selected["purchase_id"],"p_termination_date":str(termination_date),
                            "p_termination_type":"expired" if termination_label=="逾期中止" else "refund",
                            "p_charge_fee":charge_fee,"p_completion_bonus_eligible":bonus_eligible,
                            "p_completion_bonus_coach_id":coaches.get(bonus_coach),"p_reason":reason.strip(),
                            "p_note":note.strip() or None}).execute()
                        st.success("課程已中止，帳務金額已記錄；本筆不會增加執行時數。")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"課程中止失敗：{exc}")

    with history_tab:
        c1,c2,c3=st.columns(3)
        start=c1.date_input("開始日期",date.today().replace(day=1),key="termination_history_start")
        end=c2.date_input("結束日期",date.today(),key="termination_history_end")
        kind=c3.selectbox("中止類型",["全部","逾期中止","退費中止"],key="termination_history_kind")
        query=(client().table("course_terminations").select("*")
               .gte("termination_date",str(start)).lte("termination_date",str(end)).order("termination_date",desc=True))
        terminations=rows(query)
        if kind!="全部": terminations=[x for x in terminations if x["termination_type"]==("expired" if kind=="逾期中止" else "refund")]
        history_purchase_ids=list({x["purchase_id"] for x in terminations})
        history_purchases=rows(client().table("purchases").select("id,member_id,course_name").in_("id",history_purchase_ids)) if history_purchase_ids else []
        history_purchase_map={x["id"]:x for x in history_purchases}
        history_rows=[]
        for item in terminations:
            purchase=history_purchase_map.get(item["purchase_id"],{})
            history_rows.append({"中止日期":item["termination_date"],"購買_ID":purchase_code_map.get(item["purchase_id"],""),
                "會員名稱":member_name_map.get(purchase.get("member_id"),"未知"),"課程名稱":purchase.get("course_name","") ,
                "中止類型":"逾期中止" if item["termination_type"]=="expired" else "退費中止",
                "剩餘堂數":item["remaining_sessions"],"退費前剩餘金額":float(item["remaining_amount"]),
                "手續費":float(item["fee_amount"]),"實際退費金額":float(item["refund_amount"]),
                "轉列入帳金額":float(item["recognized_amount"]),"結單獎金":"計算" if item["completion_bonus_eligible"] else "不計算",
                "獎金歸屬教練":coach_name_map.get(item.get("completion_bonus_coach_id"),""),"中止原因":item.get("reason") or "","備註":item.get("note") or ""})
        history_df=pd.DataFrame(history_rows,columns=["中止日期","購買_ID","會員名稱","課程名稱","中止類型","剩餘堂數","退費前剩餘金額","手續費","實際退費金額","轉列入帳金額","結單獎金","獎金歸屬教練","中止原因","備註"])
        money_config={x:st.column_config.NumberColumn(format="$ %.0f") for x in ["退費前剩餘金額","手續費","實際退費金額","轉列入帳金額"]}
        st.dataframe(history_df,hide_index=True,width="stretch",column_config=money_config)
        export=_excel_bytes({"課程中止紀錄":history_df})
        st.download_button("匯出課程中止紀錄",export,file_name=f"課程中止紀錄_{start}_{end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")

def financial_report_page(me):
    st.header("財務報表")
    if me["role"]!="admin":
        st.warning("此頁僅限系統管理員使用。")
        return
    report_tabs=st.tabs(["會員報表","專案報表","每日營運報表","其他報表","每月報表","教練查詢","課程中止"])
    with report_tabs[0]:
        st.subheader("會員報表")
        members=rows(client().table("members").select("id,member_name").order("member_name"))
        member_name_map={x["id"]:x["member_name"] for x in members}
        member_id_map={x["member_name"]:x["id"] for x in members}
        coaches=coach_options(); coach_name_map={v:k for k,v in coaches.items()}
        c1,c2,c3,c4=st.columns(4)
        start=c1.date_input("開始日期",date.today().replace(day=1),key="finance_member_start")
        end=c2.date_input("結束日期",date.today(),key="finance_member_end")
        selected_coach=c3.selectbox("教練",["全部教練"]+list(coaches),key="finance_member_coach")
        selected_member=c4.selectbox("會員名稱",["全部會員"]+list(member_id_map),key="finance_member_name")
        if start>end:
            st.error("開始日期不可晚於結束日期。")
            return
        selected_coach_id=coaches.get(selected_coach)
        selected_member_id=member_id_map.get(selected_member)
        detail_tabs=st.tabs(["成交預收總表","預收餘額明細"])
        with detail_tabs[0]:
            total_tax_mode=st.radio("預收總額顯示方式",["未稅","含稅"],horizontal=True,key="finance_member_total_tax_mode")
        with detail_tabs[1]:
            detail_tax_mode=st.radio("預收明細金額顯示方式",["未稅","含稅"],horizontal=True,key="finance_member_detail_tax_mode")

        all_purchase_keys=rows(client().table("purchases").select("id,purchase_date,created_at").order("purchase_date"))
        financial_purchase_code_map=_build_purchase_code_map(all_purchase_keys)

        # 預收明細以付款日期判斷是否列入，包含查詢期間收到的分期款。
        period_payments=rows(client().table("purchase_payments").select("purchase_id,amount,paid_date").gte("paid_date",str(start)).lte("paid_date",str(end)).order("paid_date",desc=True))
        period_purchase_ids=list({x["purchase_id"] for x in period_payments})
        purchases=rows(client().table("purchases").select("id,member_id,coach_id,course_name,total_sessions,total_amount,purchase_date,payment_plan,installment_count").in_("id",period_purchase_ids)) if period_purchase_ids else []
        if selected_coach_id: purchases=[x for x in purchases if x.get("coach_id")==selected_coach_id]
        if selected_member_id: purchases=[x for x in purchases if x.get("member_id")==selected_member_id]
        purchase_ids=[x["id"] for x in purchases]
        period_payments=[x for x in period_payments if x["purchase_id"] in set(purchase_ids)]
        balance_usages=rows(client().table("session_usages").select("purchase_id,deducted_amount,usage_date").in_("purchase_id",purchase_ids).lte("usage_date",str(end))) if purchase_ids else []
        balance_payments=rows(client().table("purchase_payments").select("purchase_id,installment_no,amount,paid_date").in_("purchase_id",purchase_ids).lte("paid_date",str(end))) if purchase_ids else []
        used_amount_map={}
        for usage in balance_usages:
            used_amount_map[usage["purchase_id"]]=used_amount_map.get(usage["purchase_id"],0)+float(usage["deducted_amount"])
        received_amount_map={}
        paid_installments_map={}
        for payment in balance_payments:
            received_amount_map[payment["purchase_id"]]=received_amount_map.get(payment["purchase_id"],0)+float(payment["amount"])
            if payment.get("installment_no") is not None:
                paid_installments_map.setdefault(payment["purchase_id"],set()).add(int(payment["installment_no"]))
        period_received_map={}
        period_payment_date_map={}
        for payment in period_payments:
            purchase_id=payment["purchase_id"]
            period_received_map[purchase_id]=period_received_map.get(purchase_id,0)+float(payment["amount"])
            period_payment_date_map[purchase_id]=max(str(payment["paid_date"]),period_payment_date_map.get(purchase_id,""))
        balance_rows=[]
        for purchase in purchases:
            contracted=float(purchase["total_amount"])
            period_prepaid=period_received_map.get(purchase["id"],0)
            cumulative_prepaid=min(received_amount_map.get(purchase["id"],0),contracted)
            used=min(used_amount_map.get(purchase["id"],0),contracted)
            remaining=cumulative_prepaid-used
            purchase_in_period=str(start)<=str(purchase["purchase_date"])<=str(end)
            if cumulative_prepaid>=contracted:
                payment_status="付清"
            elif purchase.get("payment_plan")=="installment":
                paid_count=len(paid_installments_map.get(purchase["id"],set()))
                payment_status=f'已付 {paid_count}/{int(purchase.get("installment_count") or 0)} 期'
            else:
                payment_status="未付清"
            balance_rows.append({"日期":period_payment_date_map.get(purchase["id"]),"購買_ID":financial_purchase_code_map.get(purchase["id"],""),
                "會員名稱":member_name_map.get(purchase["member_id"],""),"課程名稱":purchase.get("course_name") or "","堂數":int(purchase.get("total_sessions") or 0),
                "分期期數／付清":payment_status,
                "成交總金額":_tax_display_amount(contracted,detail_tax_mode) if purchase_in_period else None,"實際預收金額":_tax_display_amount(period_prepaid,detail_tax_mode),
                "銷課金額":_tax_display_amount(used,detail_tax_mode),"剩餘金額":_tax_display_amount(remaining,detail_tax_mode),
                "_含稅成交":contracted if purchase_in_period else 0,"_含稅預收":period_prepaid,"_含稅銷課":used,"_含稅剩餘":remaining})
        balance_rows.sort(key=lambda x:str(x.get("日期") or ""),reverse=True)
        balance_df=pd.DataFrame(balance_rows,columns=["日期","會員名稱","成交總金額","實際預收金額","銷課金額","剩餘金額"])
        totals_df=pd.DataFrame([{"成交總金額":_tax_display_amount(sum(x["_含稅成交"] for x in balance_rows),total_tax_mode),
            "實際預收總金額":_tax_display_amount(sum(x["_含稅預收"] for x in balance_rows),total_tax_mode)}])
        prepaid_total_rows=[{
            "購買_ID":x["購買_ID"],"會員名稱":x["會員名稱"],"課程名稱":x["課程名稱"],"堂數":x["堂數"],
            "分期期數／付清":x["分期期數／付清"],
            "成交金額":_tax_display_amount(x["_含稅成交"],total_tax_mode) if x["_含稅成交"] else None,
            "實際預收金額":_tax_display_amount(x["_含稅預收"],total_tax_mode),
        } for x in balance_rows]
        prepaid_total_rows.append({
            "購買_ID":"合計","會員名稱":"","課程名稱":"","堂數":sum(x["堂數"] for x in balance_rows),"分期期數／付清":"",
            "成交金額":_tax_display_amount(sum(x["_含稅成交"] for x in balance_rows),total_tax_mode),
            "實際預收金額":_tax_display_amount(sum(x["_含稅預收"] for x in balance_rows),total_tax_mode),
        })
        prepaid_total_df=pd.DataFrame(prepaid_total_rows,columns=["購買_ID","會員名稱","課程名稱","堂數","分期期數／付清","成交金額","實際預收金額"])

        # 預收餘額明細為截至今日的即時餘額，不受上方日期區間限制。
        outstanding_purchases=rows(client().table("purchases").select("id,member_id,coach_id,course_name,total_sessions,total_amount,purchase_date,expiry_date,status")
            .in_("status",["active","completed","expired","cancelled"]).lte("purchase_date",str(date.today())).order("purchase_date",desc=True))
        if selected_coach_id: outstanding_purchases=[x for x in outstanding_purchases if x.get("coach_id")==selected_coach_id]
        if selected_member_id: outstanding_purchases=[x for x in outstanding_purchases if x.get("member_id")==selected_member_id]
        outstanding_ids=[x["id"] for x in outstanding_purchases]
        outstanding_payments=paged_rows(lambda: client().table("purchase_payments").select("id,purchase_id,amount,paid_date,created_at")
            .in_("purchase_id",outstanding_ids).lte("paid_date",str(date.today()))
            .order("paid_date").order("created_at").order("id")) if outstanding_ids else []
        outstanding_usages=paged_rows(lambda: client().table("session_usages").select("id,purchase_id,deducted_amount,usage_date,created_at")
            .in_("purchase_id",outstanding_ids).lte("usage_date",str(date.today()))
            .order("usage_date").order("created_at").order("id")) if outstanding_ids else []
        outstanding_paid_map={}; outstanding_used_map={}; outstanding_used_sessions_map={}
        for payment in outstanding_payments:
            outstanding_paid_map[payment["purchase_id"]]=outstanding_paid_map.get(payment["purchase_id"],0)+float(payment.get("amount") or 0)
        for usage in outstanding_usages:
            outstanding_used_map[usage["purchase_id"]]=outstanding_used_map.get(usage["purchase_id"],0)+float(usage.get("deducted_amount") or 0)
            outstanding_used_sessions_map[usage["purchase_id"]]=outstanding_used_sessions_map.get(usage["purchase_id"],0)+1
        outstanding_rows=[]
        status_label_map={"active":"進行中","completed":"已完成","expired":"逾期中止","cancelled":"退費中止"}
        for purchase in outstanding_purchases:
            contracted=float(purchase.get("total_amount") or 0)
            received=min(outstanding_paid_map.get(purchase["id"],0),contracted)
            used=min(outstanding_used_map.get(purchase["id"],0),contracted)
            used_sessions=outstanding_used_sessions_map.get(purchase["id"],0)
            total_sessions=int(purchase.get("total_sessions") or 0)
            remaining_sessions=max(total_sessions-used_sessions,0)
            raw_prepaid_balance=max(received-used,0)
            # 已完成、逾期中止及退費中止均視為已結清，不再列為可使用的預收餘額；
            # 但保留明細列，讓財務人員可查閱其實收、銷課及最終課程狀態。
            prepaid_balance=raw_prepaid_balance if purchase.get("status")=="active" else 0
            if purchase.get("status")=="active" and (prepaid_balance<=0 or remaining_sessions<=0): continue
            outstanding_rows.append({"成交日期":purchase.get("purchase_date"),"購買_ID":financial_purchase_code_map.get(purchase["id"],""),
                "會員名稱":member_name_map.get(purchase.get("member_id"),""),"課程名稱":purchase.get("course_name") or "",
                "實際預收金額":_tax_display_amount(received,detail_tax_mode),"累計銷課金額":_tax_display_amount(used,detail_tax_mode),
                "實際預收剩餘金額":_tax_display_amount(prepaid_balance,detail_tax_mode),"堂數":f"{used_sessions}／{total_sessions}",
                "有效期限":purchase.get("expiry_date"),
                "課程狀態":status_label_map.get(purchase.get("status"),purchase.get("status") or ""),
                "_含稅預收餘額":prepaid_balance})
        outstanding_balance_df=pd.DataFrame(outstanding_rows,columns=["成交日期","購買_ID","會員名稱","課程名稱","實際預收金額","累計銷課金額","實際預收剩餘金額","堂數","有效期限","課程狀態"])

        money_config={name:st.column_config.NumberColumn(format="$ %.0f") for name in ["未稅金額","含稅金額","成交金額","成交總金額","實際預收金額","銷課金額","剩餘金額","實際預收總金額","銷課總金額","剩餘總金額","累計銷課金額","實際預收剩餘金額"]}
        def center_member_report_columns(frame,columns):
            centered=[name for name in columns if name in frame.columns]
            styler=frame.style.set_properties(subset=centered,**{"text-align":"center"})
            header_styles=[{"selector":f"th.col_heading.level0.col{frame.columns.get_loc(name)}","props":[("text-align","center")]} for name in centered]
            return styler.set_table_styles(header_styles,overwrite=False)
        with detail_tabs[0]:
            total_values=totals_df.iloc[0]
            total_cols=st.columns(2)
            for col,name in zip(total_cols,["實際預收總金額","成交總金額"]):
                col.metric(name,f'$ {float(total_values[name]):,.0f}')
            st.caption(f"以上總金額顯示為{total_tax_mode}；成交總金額只計算本期間成交資料，實際預收總金額為本期間實際收款。")
            st.markdown("**購買課程明細**")
            st.caption("每列為查詢期間內有實際收款的購買課程，包含分期款；非本期間成交者，成交金額留白。")
            st.dataframe(center_member_report_columns(prepaid_total_df,["實際預收金額"]),hide_index=True,width="stretch",column_config=money_config)
        with detail_tabs[1]:
            actual_prepaid_balance_total=_tax_display_amount(sum(x["_含稅預收餘額"] for x in outstanding_rows),detail_tax_mode)
            st.metric(f"目前預收餘額（{detail_tax_mode}）",f"$ {actual_prepaid_balance_total:,.0f}")
            st.caption(f"本表不受上方日期區間限制，列出截至 {date.today()} 的進行中、已完成、逾期中止及退費中止課程。已完成與已中止課程視為結清，目前預收餘額顯示為 0；教練及會員篩選仍然有效。目前顯示：{detail_tax_mode}金額。")
            st.dataframe(center_member_report_columns(outstanding_balance_df,["實際預收金額","實際預收剩餘金額"]),hide_index=True,width="stretch",column_config=money_config)
        export_data=_excel_bytes({"成交預收總表":prepaid_total_df,"成交預收彙總":totals_df,"預收餘額明細":outstanding_balance_df})
        st.download_button("匯出會員財務報表",export_data,file_name=f"會員財務報表_{start}_{end}_明細{detail_tax_mode}_總額{total_tax_mode}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")

    if False:  # v1.7.6 起移除教練報表畫面，保留舊程式供歷史版本比對。
        st.subheader("教練報表")
        members=rows(client().table("members").select("id,member_name").order("member_name"))
        member_name_map={x["id"]:x["member_name"] for x in members}
        member_id_map={x["member_name"]:x["id"] for x in members}
        coaches=coach_options(); coach_name_map={v:k for k,v in coaches.items()}
        c1,c2,c3,c4=st.columns(4)
        coach_start=c1.date_input("開始日期",date.today().replace(day=1),key="finance_coach_start")
        coach_end=c2.date_input("結束日期",date.today(),key="finance_coach_end")
        coach_filter=c3.selectbox("教練",["全部教練"]+list(coaches),key="finance_coach_filter")
        coach_member_filter=c4.selectbox("會員名稱",["全部會員"]+list(member_id_map),key="finance_coach_member")
        if coach_start>coach_end:
            st.error("開始日期不可晚於結束日期。")
        else:
            selected_coach_id=coaches.get(coach_filter)
            selected_member_id=member_id_map.get(coach_member_filter)
            coach_ids=[selected_coach_id] if selected_coach_id else list(coach_name_map)
            coach_detail_tabs=st.tabs(["教練執課時數總表","會員回購"])

            usages=rows(client().table("session_usages").select("purchase_id,usage_date,coach_id").gte("usage_date",str(coach_start)).lte("usage_date",str(coach_end)))
            if selected_coach_id: usages=[x for x in usages if x.get("coach_id")==selected_coach_id]
            usage_purchase_ids=list({x["purchase_id"] for x in usages})
            usage_purchases=rows(client().table("purchases").select("id,member_id,course_name,session_hours").in_("id",usage_purchase_ids)) if usage_purchase_ids else []
            usage_purchase_map={x["id"]:x for x in usage_purchases}
            if selected_member_id:
                usages=[x for x in usages if usage_purchase_map.get(x["purchase_id"],{}).get("member_id")==selected_member_id]

            course_names=sorted({usage_purchase_map.get(x["purchase_id"],{}).get("course_name","") for x in usages if usage_purchase_map.get(x["purchase_id"],{}).get("course_name")})
            course_hours_by_coach={cid:{name:0.0 for name in course_names} for cid in coach_ids}
            for usage in usages:
                purchase=usage_purchase_map.get(usage["purchase_id"],{})
                cid=usage.get("coach_id"); course_name=purchase.get("course_name")
                if cid in course_hours_by_coach and course_name:
                    course_hours_by_coach[cid][course_name]+=float(purchase.get("session_hours") or 1)

            trial_items=rows(client().table("trial_items").select("coach_id,member_name,hours,entry_date").gte("entry_date",str(coach_start)).lte("entry_date",str(coach_end)))
            single_sales=rows(client().table("single_sales").select("coach_id,member_name,hours,entry_date").gte("entry_date",str(coach_start)).lte("entry_date",str(coach_end)))
            project_entries=rows(client().table("project_entries").select("coach_id,item_hours,quantity,entry_date").gte("entry_date",str(coach_start)).lte("entry_date",str(coach_end)))
            if selected_member_id:
                wanted_name=member_name_map.get(selected_member_id,"").strip().casefold()
                trial_items=[x for x in trial_items if str(x.get("member_name") or "").strip().casefold()==wanted_name]
                single_sales=[x for x in single_sales if str(x.get("member_name") or "").strip().casefold()==wanted_name]
                project_entries=[]

            execution_rows=[]
            for cid in coach_ids:
                course_values=course_hours_by_coach.get(cid,{})
                usage_hours=sum(course_values.values())
                trial_hours=sum(float(x.get("hours") or 0) for x in trial_items if x.get("coach_id")==cid)
                single_hours=sum(float(x.get("hours") or 0) for x in single_sales if x.get("coach_id")==cid)
                project_hours=sum(float(x.get("item_hours") or 0)*float(x.get("quantity") or 0) for x in project_entries if x.get("coach_id")==cid)
                operation_hours=trial_hours+single_hours+project_hours
                row={"教練":coach_name_map.get(cid,"未知"),**course_values,"銷課時數小計":usage_hours,
                    "體驗項目":trial_hours,"單堂銷售":single_hours,"專案":project_hours,
                    "每日營運時數小計":operation_hours,"時數總計":usage_hours+operation_hours}
                execution_rows.append(row)
            execution_columns=["教練"]+course_names+["銷課時數小計","體驗項目","單堂銷售","專案","每日營運時數小計","時數總計"]
            execution_df=pd.DataFrame(execution_rows,columns=execution_columns)

            repurchases=rows(client().table("purchases").select("member_id,coach_id,course_name,purchase_kind,purchase_date").gte("purchase_date",str(coach_start)).lte("purchase_date",str(coach_end)).order("purchase_date",desc=True))
            if selected_coach_id: repurchases=[x for x in repurchases if x.get("coach_id")==selected_coach_id]
            if selected_member_id: repurchases=[x for x in repurchases if x.get("member_id")==selected_member_id]
            repurchase_groups={}
            for purchase in repurchases:
                key=(purchase.get("coach_id"),purchase.get("member_id"),purchase.get("course_name") or "")
                group=repurchase_groups.setdefault(key,{"購買次數":0})
                group["購買次數"]+=1
            repurchase_rows=[]
            for (cid,mid,course_name),group in repurchase_groups.items():
                repurchase_rows.append({"教練":coach_name_map.get(cid,"未知"),"會員名稱":member_name_map.get(mid,"未知"),"課程名稱":course_name,
                    "購買次數":group["購買次數"]})
            repurchase_rows.sort(key=lambda x:(x["教練"],x["會員名稱"],x["課程名稱"]))
            repurchase_df=pd.DataFrame(repurchase_rows,columns=["教練","會員名稱","課程名稱","購買次數"])

            with coach_detail_tabs[0]:
                st.caption("銷課時數會依每項課程名稱分欄顯示；銷課時數小計為各課程時數合計。")
                if selected_member_id: st.caption("會員篩選僅適用可辨識會員的銷課、體驗及單堂銷售；專案因無會員欄位，篩選後不列入。")
                subtotal_columns=["銷課時數小計","每日營運時數小計"]
                execution_styler=(execution_df.style
                    .format({name:"{:.2f}" for name in execution_columns if name!="教練"})
                    .set_properties(subset=subtotal_columns,**{"background-color":"#F2F2F2","color":"#000000","font-weight":"bold"})
                    .set_properties(subset=["時數總計"],**{"background-color":"#F2F2F2","color":"#000000","font-weight":"bold"}))
                st.dataframe(execution_styler,hide_index=True,use_container_width=True)
            with coach_detail_tabs[1]:
                st.caption("購買次數依所選期間內的課程購買紀錄計算。")
                st.dataframe(repurchase_df,hide_index=True,use_container_width=True)
            coach_export=_excel_bytes({"教練執課時數總表":execution_df,"會員回購":repurchase_df})
            st.download_button("匯出教練財務報表",coach_export,file_name=f"教練財務報表_{coach_start}_{coach_end}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

    with report_tabs[3]:
        st.subheader("其他報表")
        members=rows(client().table("members").select("id,member_name").order("member_name"))
        member_name_map={x["id"]:x["member_name"] for x in members}
        member_id_map={x["member_name"]:x["id"] for x in members}
        coaches=coach_options()
        c1,c2,c3,c4=st.columns(4)
        other_start=c1.date_input("開始日期",date.today().replace(day=1),key="finance_other_start")
        other_end=c2.date_input("結束日期",date.today(),key="finance_other_end")
        other_coach=c3.selectbox("教練",["全部教練"]+list(coaches),key="finance_other_coach")
        other_member=c4.selectbox("會員名稱",["全部會員"]+list(member_id_map),key="finance_other_member")
        other_tabs=st.tabs(["醫生轉介","課程屬性","第三分頁（待建置）"])
        if other_start>other_end:
            st.error("開始日期不可晚於結束日期。")
        else:
            other_purchases=rows(client().table("purchases").select("member_id,coach_id,purchase_kind,total_amount,purchase_date,referral,course_name").gte("purchase_date",str(other_start)).lte("purchase_date",str(other_end)).order("purchase_date",desc=True))
            selected_other_coach_id=coaches.get(other_coach)
            selected_other_member_id=member_id_map.get(other_member)
            if selected_other_coach_id: other_purchases=[x for x in other_purchases if x.get("coach_id")==selected_other_coach_id]
            if selected_other_member_id: other_purchases=[x for x in other_purchases if x.get("member_id")==selected_other_member_id]
            referral_purchases=other_purchases
            referral_groups={}
            for purchase in referral_purchases:
                referral=str(purchase.get("referral") or "").strip()
                if not referral: continue
                key=(referral,purchase.get("member_id"))
                group=referral_groups.setdefault(key,{"首購":0,"續約":0,"成交總金額":0.0})
                if purchase.get("purchase_kind")=="first": group["首購"]+=1
                elif purchase.get("purchase_kind")=="renewal": group["續約"]+=1
                group["成交總金額"]+=float(purchase.get("total_amount") or 0)
            referral_rows=[{"醫生轉介":referral,"會員名稱":member_name_map.get(mid,"未知"),**values} for (referral,mid),values in referral_groups.items()]
            referral_rows.sort(key=lambda x:(x["醫生轉介"],x["會員名稱"]))
            referral_df=pd.DataFrame(referral_rows,columns=["醫生轉介","會員名稱","首購","續約","成交總金額"])
            course_catalog=rows(client().table("course_catalog").select("course_name,course_type"))
            course_type_map={str(x.get("course_name") or "").strip():str(x.get("course_type") or "未分類").strip() or "未分類" for x in course_catalog}
            course_type_totals={}
            for purchase in other_purchases:
                course_name=str(purchase.get("course_name") or "").strip()
                course_type=course_type_map.get(course_name,"未分類")
                totals=course_type_totals.setdefault(course_type,{"purchase":0.0,"usage":0.0})
                totals["purchase"]+=float(purchase.get("total_amount") or 0)

            # 銷課依實際銷課日期、授課教練篩選；會員與課程屬性則由原購買紀錄關聯。
            usage_purchase_records=rows(client().table("purchases").select("id,member_id,course_name"))
            usage_purchase_map={x["id"]:x for x in usage_purchase_records}
            course_type_usages=[]
            usage_page_size=1000
            usage_offset=0
            while True:
                usage_query=(client().table("session_usages").select("purchase_id,coach_id,deducted_amount,usage_date,id")
                    .gte("usage_date",str(other_start)).lte("usage_date",str(other_end))
                    .order("usage_date",desc=True).order("id",desc=True)
                    .range(usage_offset,usage_offset+usage_page_size-1))
                if selected_other_coach_id:
                    usage_query=usage_query.eq("coach_id",selected_other_coach_id)
                usage_page=rows(usage_query)
                course_type_usages.extend(usage_page)
                if len(usage_page)<usage_page_size:
                    break
                usage_offset+=usage_page_size
            if selected_other_member_id:
                course_type_usages=[x for x in course_type_usages
                    if usage_purchase_map.get(x.get("purchase_id"),{}).get("member_id")==selected_other_member_id]
            for usage in course_type_usages:
                purchase=usage_purchase_map.get(usage.get("purchase_id"),{})
                course_name=str(purchase.get("course_name") or "").strip()
                course_type=course_type_map.get(course_name,"未分類")
                totals=course_type_totals.setdefault(course_type,{"purchase":0.0,"usage":0.0})
                totals["usage"]+=float(usage.get("deducted_amount") or 0)
            course_type_rows=[]
            for course_type,totals in sorted(course_type_totals.items()):
                course_type_rows.append({
                    "課程屬性":course_type,
                    "成交未稅金額":_tax_display_amount(totals["purchase"],"未稅"),
                    "銷課未稅金額":_tax_display_amount(totals["usage"],"未稅"),
                })
            course_type_columns=["課程屬性","成交未稅金額","銷課未稅金額"]
            course_type_df=pd.DataFrame(course_type_rows,columns=course_type_columns)
            with other_tabs[0]:
                st.caption("日期依課程購買日期；成交總金額為含稅金額。首購與續約欄位為購買筆數。")
                st.dataframe(referral_df,hide_index=True,use_container_width=True,column_config={"成交總金額":st.column_config.NumberColumn(format="$ %.0f")})
            with other_tabs[1]:
                st.caption("成交未稅金額依購買日期及成交教練；銷課未稅金額依銷課日期及實際授課教練。未稅金額均以原含稅金額 ÷ 1.05 計算。")
                if course_type_df.empty:
                    st.info("查詢期間沒有成交或銷課資料。")
                else:
                    st.dataframe(course_type_df,hide_index=True,use_container_width=True,column_config={
                        name:st.column_config.NumberColumn(format="$ %.0f") for name in course_type_columns[1:]
                    })
            with other_tabs[2]:
                st.info("此分頁將依後續需求建置。")
            other_export=_excel_bytes({"醫生轉介":referral_df,"課程屬性":course_type_df})
            st.download_button("匯出其他報表",other_export,file_name=f"其他報表_{other_start}_{other_end}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)

    with report_tabs[1]:
        st.subheader("專案報表")
        try:
            report_projects=rows(client().table("projects").select("id,project_name,funding_type,stored_amount").order("project_name"))
        except Exception:
            st.error("專案報表尚未建立，請先執行 migration_project_v1_1_0.sql。")
            report_projects=[]
        if report_projects:
            project_name_id={x["project_name"]:x["id"] for x in report_projects}
            c1,c2,c3,c4=st.columns(4)
            project_start=c1.date_input("開始日期",date.today().replace(day=1),key="finance_project_start")
            project_end=c2.date_input("結束日期",date.today(),key="finance_project_end")
            project_filter=c3.selectbox("專案名稱",["全部專案"]+list(project_name_id),key="finance_project_filter")
            project_user_filter=c4.text_input("使用者",placeholder="可輸入部分姓名",key="finance_project_user").strip().casefold()
            if project_start>project_end:
                st.error("開始日期不可晚於結束日期。")
            else:
                selected_project_id=project_name_id.get(project_filter)
                entries=rows(client().table("project_entries").select("entry_date,project_id,project_name,person_name,item_name,item_hours,quantity,unit_price,line_amount,note")
                    .gte("entry_date",str(project_start)).lte("entry_date",str(project_end)).order("entry_date",desc=True))
                if selected_project_id: entries=[x for x in entries if x.get("project_id")==selected_project_id]
                if project_user_filter: entries=[x for x in entries if project_user_filter in str(x.get("person_name") or "").casefold()]
                project_by_id={x["id"]:x for x in report_projects}
                detail_rows=[]
                for x in entries:
                    detail_rows.append({"日期":x["entry_date"],"專案名稱":x["project_name"],"使用者":x["person_name"],
                        "操作項目":x["item_name"],"時數":float(x.get("item_hours") or 0)*float(x.get("quantity") or 0),
                        "金額":int(Decimal(str(x.get("line_amount") or 0)).quantize(Decimal("1"),rounding=ROUND_HALF_UP)),
                        "備註":x.get("note") or "","_funding_type":project_by_id.get(x.get("project_id"),{}).get("funding_type")})
                stored_detail_df=pd.DataFrame([{k:v for k,v in x.items() if k!="_funding_type"} for x in detail_rows if x["_funding_type"]=="stored"],
                    columns=["日期","專案名稱","使用者","操作項目","時數","金額","備註"])
                unfunded_detail_df=pd.DataFrame([{k:v for k,v in x.items() if k!="_funding_type"} for x in detail_rows if x["_funding_type"]=="unfunded"],
                    columns=["日期","專案名稱","使用者","操作項目","時數","金額","備註"])

                stored_projects=[x for x in report_projects if x["funding_type"]=="stored" and (not selected_project_id or x["id"]==selected_project_id)]
                stored_ids=[x["id"] for x in stored_projects]
                deposit_records=rows(client().table("project_deposits").select("project_id,deposit_date,amount,transaction_type,note")
                    .in_("project_id",stored_ids).lte("deposit_date",str(date.today()))
                    .order("deposit_date",desc=True)) if stored_ids else []
                deposit_df=pd.DataFrame([{"儲值日期":x["deposit_date"],"專案名稱":project_by_id.get(x["project_id"],{}).get("project_name","未知"),
                    "類型":{"opening":"期初儲值","deposit":"後續儲值","reversal":"沖銷"}.get(x["transaction_type"],x["transaction_type"]),
                    "儲值金額":round(float(x.get("amount") or 0)),"備註":x.get("note") or ""} for x in deposit_records],
                    columns=["儲值日期","專案名稱","類型","儲值金額","備註"])
                cumulative=rows(client().table("project_entries").select("project_id,line_amount,entry_date").in_("project_id",stored_ids).lte("entry_date",str(date.today()))) if stored_ids else []
                used_by_project={}
                for x in cumulative:
                    used_by_project[x["project_id"]]=used_by_project.get(x["project_id"],0)+float(x.get("line_amount") or 0)
                funding_rows=[]
                for project in stored_projects:
                    stored=float(project["stored_amount"]); used=used_by_project.get(project["id"],0)
                    funding_rows.append({"專案名稱":project["project_name"],"儲值金額":round(stored),
                        "已使用金額":round(used),"剩餘金額":round(stored-used)})
                funding_df=pd.DataFrame(funding_rows,columns=["專案名稱","儲值金額","已使用金額","剩餘金額"])

                project_money_config={name:st.column_config.NumberColumn(format="$ %.0f") for name in ["金額","儲值金額","已使用金額","剩餘金額"]}
                project_main_tabs=st.tabs(["儲值明細","專案報表"])
                with project_main_tabs[0]:
                    st.caption(f"儲值狀況與儲值交易明細固定統計至 {date.today()}，不受上方開始／結束日期影響；專案名稱篩選仍然有效。")
                    st.markdown("#### 儲值狀況")
                    st.dataframe(funding_df,hide_index=True,width="stretch",column_config=project_money_config)
                    st.markdown("#### 儲值明細")
                    st.dataframe(deposit_df,hide_index=True,width="stretch",column_config=project_money_config)
                    deposit_export=_excel_bytes({"儲值狀況":funding_df,"儲值明細":deposit_df})
                    st.download_button("下載儲值明細",deposit_export,file_name=f"專案儲值明細_截至_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
                with project_main_tabs[1]:
                    project_usage_tabs=st.tabs(["已儲值","未儲值"])
                    with project_usage_tabs[0]:
                        st.markdown("#### 已儲值專案使用明細")
                        st.dataframe(stored_detail_df,hide_index=True,width="stretch",column_config=project_money_config)
                        stored_export=_excel_bytes({"已儲值使用明細":stored_detail_df})
                        st.download_button("下載已儲值使用明細",stored_export,file_name=f"已儲值專案使用明細_{project_start}_{project_end}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
                    with project_usage_tabs[1]:
                        st.markdown("#### 未儲值專案使用明細")
                        st.dataframe(unfunded_detail_df,hide_index=True,width="stretch",column_config=project_money_config)
                        unfunded_export=_excel_bytes({"未儲值使用明細":unfunded_detail_df})
                        st.download_button("下載未儲值使用明細",unfunded_export,file_name=f"未儲值專案使用明細_{project_start}_{project_end}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
                project_export=_excel_bytes({"儲值明細":deposit_df,"已儲值使用明細":stored_detail_df,"儲值狀況":funding_df,"未儲值使用明細":unfunded_detail_df})
                st.download_button("下載完整專案財務報表",project_export,file_name=f"專案財務報表_{project_start}_{project_end}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")

    with report_tabs[2]:
        st.subheader("每日營運報表")
        daily_coaches=coach_options()
        c1,c2,c3,c4=st.columns(4)
        daily_report_start=c1.date_input("開始日期",date.today().replace(day=1),key="finance_daily_start")
        daily_report_end=c2.date_input("結束日期",date.today(),key="finance_daily_end")
        daily_report_coach=c3.selectbox("教練",["全部教練"]+list(daily_coaches),key="finance_daily_coach")
        daily_report_member=c4.text_input("會員名稱",placeholder="可輸入完整或部分姓名",key="finance_daily_member").strip().casefold()
        if daily_report_start>daily_report_end:
            st.error("開始日期不可晚於結束日期。")
        else:
            daily_trial_records=paged_rows(lambda: client().table("trial_items")
                .select("id,entry_date,coach_id,member_name,course_type,amount")
                .gte("entry_date",str(daily_report_start)).lte("entry_date",str(daily_report_end))
                .order("entry_date",desc=True).order("id",desc=True))
            daily_single_records=paged_rows(lambda: client().table("single_sales")
                .select("id,entry_date,coach_id,member_name,course_type,amount")
                .gte("entry_date",str(daily_report_start)).lte("entry_date",str(daily_report_end))
                .order("entry_date",desc=True).order("id",desc=True))
            selected_daily_coach_id=daily_coaches.get(daily_report_coach)
            if selected_daily_coach_id:
                daily_trial_records=[x for x in daily_trial_records if x.get("coach_id")==selected_daily_coach_id]
                daily_single_records=[x for x in daily_single_records if x.get("coach_id")==selected_daily_coach_id]
            if daily_report_member:
                daily_trial_records=[x for x in daily_trial_records if daily_report_member in str(x.get("member_name") or "").casefold()]
                daily_single_records=[x for x in daily_single_records if daily_report_member in str(x.get("member_name") or "").casefold()]

            def operation_finance_summary(records):
                amount_by_course_type={}
                for record in records:
                    course_type=str(record.get("course_type") or "未分類").strip() or "未分類"
                    amount_by_course_type[course_type]=amount_by_course_type.get(course_type,Decimal("0"))+Decimal(str(record.get("amount") or 0))
                summary_rows=[]
                for course_type,amount in sorted(amount_by_course_type.items()):
                    summary_rows.append({"課程屬性":course_type,
                        "未稅金額":int(amount.quantize(Decimal("1"),rounding=ROUND_HALF_UP))})
                return pd.DataFrame(summary_rows,columns=["課程屬性","未稅金額"])

            daily_trial_df=operation_finance_summary(daily_trial_records)
            daily_single_df=operation_finance_summary(daily_single_records)
            daily_money_config={"未稅金額":st.column_config.NumberColumn(format="$ %.0f")}
            daily_operation_tabs=st.tabs(["體驗項目報表","單堂銷售報表"])
            with daily_operation_tabs[0]:
                daily_trial_total=int(daily_trial_df["未稅金額"].sum()) if not daily_trial_df.empty else 0
                st.metric("體驗總計（未稅）",f"$ {daily_trial_total:,.0f}")
                st.dataframe(daily_trial_df,hide_index=True,width="stretch",height="auto",row_height=28,column_config=daily_money_config)
                daily_trial_export=_excel_bytes({"體驗項目報表":daily_trial_df})
                st.download_button("下載體驗項目報表",daily_trial_export,
                    file_name=f"體驗項目報表_{daily_report_start}_{daily_report_end}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
            with daily_operation_tabs[1]:
                daily_single_total=int(daily_single_df["未稅金額"].sum()) if not daily_single_df.empty else 0
                st.metric("單堂銷售總計（未稅）",f"$ {daily_single_total:,.0f}")
                st.dataframe(daily_single_df,hide_index=True,width="stretch",height="auto",row_height=28,column_config=daily_money_config)
                daily_single_export=_excel_bytes({"單堂銷售報表":daily_single_df})
                st.download_button("下載單堂銷售報表",daily_single_export,
                    file_name=f"單堂銷售報表_{daily_report_start}_{daily_report_end}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
            daily_operation_export=_excel_bytes({"體驗項目報表":daily_trial_df,"單堂銷售報表":daily_single_df})
            st.download_button("下載每日營運報表",daily_operation_export,
                file_name=f"每日營運報表_{daily_report_start}_{daily_report_end}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")

    with report_tabs[4]:
        st.subheader("每月報表")
        default_month_start=date.today().replace(day=1)
        default_month_end=(pd.Timestamp(default_month_start)+pd.offsets.MonthEnd(1)).date()
        c1,c2=st.columns(2)
        month_start=c1.date_input("開始日期",default_month_start,key="monthly_report_start")
        month_end=c2.date_input("結束日期",default_month_end,key="monthly_report_end")
        if month_start>month_end:
            st.error("開始日期不可晚於結束日期。")
            st.stop()
        st.markdown(f"- 報表期間：{month_start} 至 {month_end}")

        monthly_coaches=coach_options(); monthly_coach_name={v:k for k,v in monthly_coaches.items()}
        monthly_usages=rows(client().table("session_usages").select("purchase_id,usage_date,coach_id,session_seq,deducted_amount")
            .gte("usage_date",str(month_start)).lte("usage_date",str(month_end)).order("usage_date"))
        try:
            monthly_terminations=rows(client().table("course_terminations").select("purchase_id,termination_date,termination_type,remaining_amount,fee_amount,refund_amount,recognized_amount,completion_bonus_eligible,completion_bonus_coach_id,reason")
                .gte("termination_date",str(month_start)).lte("termination_date",str(month_end)).order("termination_date"))
        except Exception:
            monthly_terminations=[]
        monthly_purchase_ids=list({x["purchase_id"] for x in monthly_usages+monthly_terminations})
        monthly_purchases=rows(client().table("purchases").select("id,member_id,coach_id,course_name,session_hours,total_sessions,total_amount,purchase_date,purchase_kind,referral,created_at").in_("id",monthly_purchase_ids)) if monthly_purchase_ids else []
        monthly_purchase_map={x["id"]:x for x in monthly_purchases}
        monthly_member_ids=list({x.get("member_id") for x in monthly_purchases if x.get("member_id")})
        monthly_members=rows(client().table("members").select("id,member_name").in_("id",monthly_member_ids)) if monthly_member_ids else []
        monthly_member_name={x["id"]:x["member_name"] for x in monthly_members}
        monthly_trial=rows(client().table("trial_items").select("entry_date,coach_id,content,course_type,hours,amount").gte("entry_date",str(month_start)).lte("entry_date",str(month_end)).order("entry_date"))
        monthly_single=rows(client().table("single_sales").select("entry_date,coach_id,content,course_type,hours,amount").gte("entry_date",str(month_start)).lte("entry_date",str(month_end)).order("entry_date"))
        monthly_events=rows(client().table("event_supports").select("entry_date,coach_id,hours,deducted_hours").gte("entry_date",str(month_start)).lte("entry_date",str(month_end)).order("entry_date"))
        monthly_projects=rows(client().table("project_entries").select("entry_date,project_id,project_name,person_name,coach_id,item_hours,quantity,line_amount")
            .gte("entry_date",str(month_start)).lte("entry_date",str(month_end)).order("entry_date"))
        monthly_project_ids=list({x.get("project_id") for x in monthly_projects if x.get("project_id")})
        monthly_project_master=rows(client().table("projects").select("id,funding_type").in_("id",monthly_project_ids)) if monthly_project_ids else []
        monthly_project_type={x["id"]:x["funding_type"] for x in monthly_project_master}

        monthly_sales_df=pd.DataFrame([{"日期":x["usage_date"],"姓名":monthly_member_name.get(monthly_purchase_map.get(x["purchase_id"],{}).get("member_id"),"未知"),
            "銷課金額":_tax_display_amount(x.get("deducted_amount"),"未稅"),
            "購買堂數":int(monthly_purchase_map.get(x["purchase_id"],{}).get("total_sessions") or 0),
            "購買課程":monthly_purchase_map.get(x["purchase_id"],{}).get("course_name") or ""} for x in monthly_usages],
            columns=["日期","姓名","銷課金額","購買堂數","購買課程"])
        monthly_stored_project_df=pd.DataFrame([{"專案":x["project_name"],"日期":x["entry_date"],"姓名":x.get("person_name") or "",
            "扣款金額（未稅）":_tax_display_amount(x.get("line_amount"),"未稅")} for x in monthly_projects if monthly_project_type.get(x.get("project_id"))=="stored"],
            columns=["專案","日期","姓名","扣款金額（未稅）"])
        all_purchase_keys=rows(client().table("purchases").select("id,purchase_date,created_at").order("purchase_date"))
        bonus_purchase_code_map=_build_purchase_code_map(all_purchase_keys)
        monthly_termination_rows=[]
        for item in monthly_terminations:
            purchase=monthly_purchase_map.get(item["purchase_id"],{})
            is_expired=item.get("termination_type")=="expired"
            monthly_termination_rows.append({"日期":item["termination_date"],"購買_ID":bonus_purchase_code_map.get(item["purchase_id"],""),
                "會員名稱":monthly_member_name.get(purchase.get("member_id"),"未知"),"課程名稱":purchase.get("course_name") or "",
                "中止類型":"逾期中止" if is_expired else "退費中止",
                "退費前剩餘金額（未稅）":_tax_display_amount(item.get("remaining_amount"),"未稅"),
                "逾期入帳金額（未稅）":_tax_display_amount(item.get("recognized_amount"),"未稅") if is_expired else 0,
                "退費手續費（未稅）":_tax_display_amount(item.get("fee_amount"),"未稅") if not is_expired else 0,
                "實際退費金額（未稅）":_tax_display_amount(item.get("refund_amount"),"未稅") if not is_expired else 0,
                "中止原因":item.get("reason") or ""})
        monthly_termination_df=pd.DataFrame(monthly_termination_rows,columns=["日期","購買_ID","會員名稱","課程名稱","中止類型","退費前剩餘金額（未稅）","逾期入帳金額（未稅）","退費手續費（未稅）","實際退費金額（未稅）","中止原因"])

        coach_ids=list(monthly_coaches.values())
        coach_hour_rows=[]; coach_revenue_rows=[]
        for coach_id in coach_ids:
            coach_trials=[x for x in monthly_trial if x.get("coach_id")==coach_id]
            coach_singles=[x for x in monthly_single if x.get("coach_id")==coach_id]
            trial_hours=sum(float(x.get("hours") or 0) for x in coach_trials if not is_magnetic_wave_operation(x))
            single_hours=sum(float(x.get("hours") or 0) for x in coach_singles if not is_magnetic_wave_operation(x))
            event_hours=sum(max(0,float(x.get("hours") or 0)-float(x.get("deducted_hours") or 0)) for x in monthly_events if x.get("coach_id")==coach_id)
            project_hours=sum(float(x.get("item_hours") or 0)*float(x.get("quantity") or 0) for x in monthly_projects if x.get("coach_id")==coach_id)
            coach_usages=[x for x in monthly_usages if x.get("coach_id")==coach_id]
            usage_hours=sum(float(monthly_purchase_map.get(x["purchase_id"],{}).get("session_hours") or 1) for x in coach_usages
                if not is_magnetic_wave_course(monthly_purchase_map.get(x["purchase_id"],{}).get("course_name")))
            magnetic_wave_hours=(sum(float(x.get("hours") or 0) for x in coach_trials if is_magnetic_wave_operation(x))
                +sum(float(x.get("hours") or 0) for x in coach_singles if is_magnetic_wave_operation(x))
                +sum(float(monthly_purchase_map.get(x["purchase_id"],{}).get("session_hours") or 1) for x in coach_usages
                    if is_magnetic_wave_course(monthly_purchase_map.get(x["purchase_id"],{}).get("course_name"))))
            coach_hour_rows.append({"教練":monthly_coach_name.get(coach_id,"未知"),"體驗時數":trial_hours,"單堂時數":single_hours,
                "活動時數":event_hours,"專案時數":project_hours,"銷課時數":usage_hours,
                "可計執行時數":trial_hours+single_hours+event_hours+project_hours+usage_hours,"動磁波時數":magnetic_wave_hours})
            trial_revenue=sum(float(x.get("amount") or 0) for x in coach_trials)
            single_revenue=sum(float(x.get("amount") or 0) for x in coach_singles)
            project_revenue=sum(_tax_display_amount(x.get("line_amount"),"未稅") for x in monthly_projects if x.get("coach_id")==coach_id)
            usage_revenue=sum(_tax_display_amount(x.get("deducted_amount"),"未稅") for x in monthly_usages if x.get("coach_id")==coach_id)
            coach_revenue_rows.append({"教練":monthly_coach_name.get(coach_id,"未知"),"體驗項目金額（未稅）":round(trial_revenue),"單堂銷售金額（未稅）":round(single_revenue),
                "專案（未稅）":round(project_revenue),"銷課（未稅）":round(usage_revenue),"金額總計（未稅）":round(trial_revenue+single_revenue+project_revenue+usage_revenue)})
        monthly_hours_df=pd.DataFrame(coach_hour_rows,columns=["教練","體驗時數","單堂時數","活動時數","專案時數","銷課時數","可計執行時數","動磁波時數"])
        monthly_revenue_df=pd.DataFrame(coach_revenue_rows,columns=["教練","體驗項目金額（未稅）","單堂銷售金額（未稅）","專案（未稅）","銷課（未稅）","金額總計（未稅）"])

        try:
            bonus_rules=rows(client().table("bonus_rules").select("*").eq("active",True).order("effective_from",desc=True))
            bonus_rule_error=False
        except Exception:
            bonus_rules=[]; bonus_rule_error=True

        talk_purchases=rows(client().table("purchases").select("id,member_id,coach_id,course_name,total_amount,purchase_date,purchase_kind,referral,created_at")
            .gte("purchase_date",str(month_start)).lte("purchase_date",str(month_end)).order("purchase_date"))
        bonus_member_ids=list({x.get("member_id") for x in monthly_purchases+talk_purchases if x.get("member_id")})
        missing_member_ids=[x for x in bonus_member_ids if x not in monthly_member_name]
        if missing_member_ids:
            for member in rows(client().table("members").select("id,member_name").in_("id",missing_member_ids)):
                monthly_member_name[member["id"]]=member["member_name"]
        talk_bonus_rows=[]
        for purchase in talk_purchases:
            coach_id=purchase.get("coach_id")
            if coach_id not in coach_ids: continue
            rule=_bonus_rule_for_date(bonus_rules,purchase["purchase_date"])
            eligible,reason=_bonus_eligibility(rule,purchase,"talk")
            untaxed_amount=_tax_display_amount(purchase.get("total_amount"),"未稅")
            rate=Decimal(str(rule.get("talk_rate") or 0)) if rule else Decimal("0")
            bonus=int((Decimal(untaxed_amount)*rate).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) if eligible else 0
            talk_bonus_rows.append({"成交日期":purchase["purchase_date"],"購買_ID":bonus_purchase_code_map.get(purchase["id"],""),
                "會員名稱":monthly_member_name.get(purchase.get("member_id"),"未知"),"教練":monthly_coach_name.get(coach_id,"未知"),
                "購買類型":"首次購買" if purchase.get("purchase_kind")=="first" else "續約" if purchase.get("purchase_kind")=="renewal" else purchase.get("purchase_kind") or "",
                "醫生轉介":purchase.get("referral") or "","成交未稅金額":untaxed_amount,"談單率":float(rate)*100,
                "談單獎金":bonus,"適用規則":rule.get("rule_name") if rule else "","計算狀態":"已計算" if eligible else reason})
        talk_bonus_columns=["成交日期","購買_ID","會員名稱","教練","購買類型","醫生轉介","成交未稅金額","談單率","談單獎金","適用規則","計算狀態"]
        monthly_talk_bonus_df=pd.DataFrame(talk_bonus_rows,columns=talk_bonus_columns)
        talk_bonus_summary_rows=[]
        for coach_id in coach_ids:
            coach_name=monthly_coach_name.get(coach_id,"未知")
            eligible_rows=[x for x in talk_bonus_rows if x["教練"]==coach_name and x["計算狀態"]=="已計算"]
            talk_bonus_summary_rows.append({"教練":coach_name,
                "符合規則成交未稅金額總計":sum(x["成交未稅金額"] for x in eligible_rows),
                "談單獎金總計":sum(x["談單獎金"] for x in eligible_rows)})
        monthly_talk_bonus_summary_df=pd.DataFrame(talk_bonus_summary_rows,
            columns=["教練","符合規則成交未稅金額總計","談單獎金總計"])

        completed_purchase_usage={}
        for usage in monthly_usages:
            purchase=monthly_purchase_map.get(usage["purchase_id"],{})
            total_sessions=int(purchase.get("total_sessions") or 0)
            if total_sessions and int(usage.get("session_seq") or 0)==total_sessions:
                completed_purchase_usage[usage["purchase_id"]]=usage
        completion_bonus_rows=[]
        for purchase_id,usage in completed_purchase_usage.items():
            purchase=monthly_purchase_map[purchase_id]
            coach_id=usage.get("coach_id")
            if coach_id not in coach_ids: continue
            rule=_bonus_rule_for_date(bonus_rules,usage["usage_date"])
            eligible,reason=_bonus_eligibility(rule,purchase,"completion")
            completed_amount=_tax_display_amount(purchase.get("total_amount"),"未稅")
            rate=Decimal(str(rule.get("completion_rate") or 0)) if rule else Decimal("0")
            bonus=int((Decimal(completed_amount)*rate).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) if eligible else 0
            completion_bonus_rows.append({"課程完成日期":usage["usage_date"],"購買_ID":bonus_purchase_code_map.get(purchase_id,""),
                "會員名稱":monthly_member_name.get(purchase.get("member_id"),"未知"),"教練":monthly_coach_name.get(coach_id,"未知"),
                "課程名稱":purchase.get("course_name") or "","購買類型":"首次購買" if purchase.get("purchase_kind")=="first" else "續約" if purchase.get("purchase_kind")=="renewal" else purchase.get("purchase_kind") or "",
                "醫生轉介":purchase.get("referral") or "","課程結束成交未稅金額":completed_amount,"結單率":float(rate)*100,
                "結單獎金":bonus,"適用規則":rule.get("rule_name") if rule else "","計算狀態":"已計算" if eligible else reason})
        for termination in monthly_terminations:
            purchase=monthly_purchase_map.get(termination["purchase_id"],{})
            coach_id=termination.get("completion_bonus_coach_id")
            if termination.get("termination_type")!="expired" or not termination.get("completion_bonus_eligible") or coach_id not in coach_ids:
                continue
            rule=_bonus_rule_for_date(bonus_rules,termination["termination_date"])
            eligible,reason=_bonus_eligibility(rule,purchase,"completion")
            completed_amount=_tax_display_amount(purchase.get("total_amount"),"未稅")
            rate=Decimal(str(rule.get("completion_rate") or 0)) if rule else Decimal("0")
            bonus=int((Decimal(completed_amount)*rate).quantize(Decimal("1"),rounding=ROUND_HALF_UP)) if eligible else 0
            completion_bonus_rows.append({"課程完成日期":termination["termination_date"],"購買_ID":bonus_purchase_code_map.get(termination["purchase_id"],""),
                "會員名稱":monthly_member_name.get(purchase.get("member_id"),"未知"),"教練":monthly_coach_name.get(coach_id,"未知"),
                "課程名稱":purchase.get("course_name") or "","購買類型":"首次購買" if purchase.get("purchase_kind")=="first" else "續約" if purchase.get("purchase_kind")=="renewal" else purchase.get("purchase_kind") or "",
                "醫生轉介":purchase.get("referral") or "","課程結束成交未稅金額":completed_amount,"結單率":float(rate)*100,
                "結單獎金":bonus,"適用規則":rule.get("rule_name") if rule else "","計算狀態":"已計算" if eligible else reason})
        completion_bonus_columns=["課程完成日期","購買_ID","會員名稱","教練","課程名稱","購買類型","醫生轉介","課程結束成交未稅金額","結單率","結單獎金","適用規則","計算狀態"]
        monthly_completion_bonus_df=pd.DataFrame(completion_bonus_rows,columns=completion_bonus_columns)
        completion_bonus_summary_rows=[]
        for coach_id in coach_ids:
            coach_name=monthly_coach_name.get(coach_id,"未知")
            eligible_rows=[x for x in completion_bonus_rows if x["教練"]==coach_name and x["計算狀態"]=="已計算"]
            completion_bonus_summary_rows.append({"教練":coach_name,
                "符合規則課程結束成交未稅金額總計":sum(x["課程結束成交未稅金額"] for x in eligible_rows),
                "結單獎金總計":sum(x["結單獎金"] for x in eligible_rows)})
        monthly_completion_bonus_summary_df=pd.DataFrame(completion_bonus_summary_rows,
            columns=["教練","符合規則課程結束成交未稅金額總計","結單獎金總計"])

        monthly_tabs=st.tabs(["每月銷課","每月專案銷課","每月課程中止","每月教練時數","每月教練營收","每月教練談單獎金","每月教練結單獎金"])
        monthly_money_config={name:st.column_config.NumberColumn(format="$ %.0f") for name in ["銷課金額","扣款金額（未稅）","體驗項目金額（未稅）","單堂銷售金額（未稅）","專案（未稅）","銷課（未稅）","金額總計（未稅）","成交未稅金額","談單獎金","課程結束成交未稅金額","結單獎金","符合規則成交未稅金額總計","談單獎金總計","符合規則課程結束成交未稅金額總計","結單獎金總計","退費前剩餘金額（未稅）","逾期入帳金額（未稅）","退費手續費（未稅）","實際退費金額（未稅）"]}
        monthly_bonus_config={**monthly_money_config,"談單率":st.column_config.NumberColumn(format="%.2f%%"),"結單率":st.column_config.NumberColumn(format="%.2f%%")}
        with monthly_tabs[0]:
            monthly_sales_total=int(monthly_sales_df["銷課金額"].sum()) if not monthly_sales_df.empty else 0
            st.metric("銷課總金額（未稅）",f"$ {monthly_sales_total:,.0f}")
            st.caption("※銷課金額為未稅金額。")
            st.dataframe(monthly_sales_df,hide_index=True,width="stretch",column_config=monthly_money_config)
        with monthly_tabs[1]:
            monthly_project_total=int(monthly_stored_project_df["扣款金額（未稅）"].sum()) if not monthly_stored_project_df.empty else 0
            st.metric("專案總金額（未稅）",f"$ {monthly_project_total:,.0f}")
            st.dataframe(monthly_stored_project_df,hide_index=True,width="stretch",column_config=monthly_money_config)
        with monthly_tabs[2]:
            expired_total=int(monthly_termination_df["逾期入帳金額（未稅）"].sum()) if not monthly_termination_df.empty else 0
            fee_total=int(monthly_termination_df["退費手續費（未稅）"].sum()) if not monthly_termination_df.empty else 0
            refund_total=int(monthly_termination_df["實際退費金額（未稅）"].sum()) if not monthly_termination_df.empty else 0
            c1,c2,c3=st.columns(3)
            c1.metric("逾期入帳總額（未稅）",f"$ {expired_total:,.0f}")
            c2.metric("退費手續費總額（未稅）",f"$ {fee_total:,.0f}")
            c3.metric("實際退費總額（未稅）",f"$ {refund_total:,.0f}")
            st.dataframe(monthly_termination_df,hide_index=True,width="stretch",column_config=monthly_money_config)
        with monthly_tabs[3]:
            st.caption("※可計執行時數不含動磁波；動磁波時數包含體驗、單堂銷售及課程銷課。")
            st.dataframe(monthly_hours_df,hide_index=True,width="stretch")
        with monthly_tabs[4]:
            st.caption("※體驗項目及單堂銷售金額使用系統輸入的未稅金額。")
            st.dataframe(monthly_revenue_df,hide_index=True,width="stretch",column_config=monthly_money_config)
        with monthly_tabs[5]:
            if bonus_rule_error: st.error("尚未建立獎金規則資料表，請先執行 migration_bonus_rules_v1_8_0.sql。")
            st.dataframe(monthly_talk_bonus_df,hide_index=True,width="stretch",column_config=monthly_bonus_config)
            st.markdown("**各教練談單獎金總計**")
            st.dataframe(monthly_talk_bonus_summary_df,hide_index=True,width="stretch",column_config=monthly_bonus_config)
        with monthly_tabs[6]:
            if bonus_rule_error: st.error("尚未建立獎金規則資料表，請先執行 migration_bonus_rules_v1_8_0.sql。")
            st.dataframe(monthly_completion_bonus_df,hide_index=True,width="stretch",column_config=monthly_bonus_config)
            st.markdown("**各教練結單獎金總計**")
            st.dataframe(monthly_completion_bonus_summary_df,hide_index=True,width="stretch",column_config=monthly_bonus_config)
        monthly_export=_excel_bytes({"每月銷課":monthly_sales_df,"每月專案銷課":monthly_stored_project_df,
            "每月課程中止":monthly_termination_df,"每月教練時數":monthly_hours_df,"每月教練營收":monthly_revenue_df,
            "每月教練談單獎金":monthly_talk_bonus_df,"談單獎金總計":monthly_talk_bonus_summary_df,
            "每月教練結單獎金":monthly_completion_bonus_df,"結單獎金總計":monthly_completion_bonus_summary_df})
        st.download_button("匯出每月報表",monthly_export,file_name=f"每月報表_{month_start}_{month_end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")

    with report_tabs[5]:
        usage_query_tabs(me,enable_export=True)

    with report_tabs[6]:
        course_termination_report_page(me)

user=login(); me=profile(user.id)
with st.sidebar:
    st.title("🏋️ 營運管理")
    st.write(f'{me["display_name"]}｜{ROLE_LABELS.get(me["role"],me["role"])}')
    pages=["每日營運","課程購買","銷課表"]
    if me["role"] in ("manager","admin"): pages.append("主管 Dashboard")
    if me["role"] == "admin":
        pages.extend(["財務報表", "帳號與權限管理", "資料管理"])
    page=st.radio("功能",pages)
    if st.button("登出"):
        client().auth.sign_out(); st.session_state.clear(); st.rerun()

collapse_sidebar_on_mobile()

try:
    {"每日營運":daily_page,"課程購買":purchase_page,"銷課表":usage_page,"主管 Dashboard":dashboard_page,"財務報表":financial_report_page,"帳號與權限管理":account_admin_page,"資料管理":data_management_page}[page](me)
except Exception as exc:
    st.error(f"讀取資料時發生錯誤：{exc}")

