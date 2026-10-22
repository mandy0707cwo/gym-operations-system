"""選單及分頁路由；只執行目前開啟的內容，不讀寫資料庫。"""
import streamlit as st

DAILY_TABS = ("銷課登錄", "體驗登錄", "單堂銷售", "專案登錄", "活動支援")
FINANCE_TABS = ("各項查詢", "每月查詢")
ADMIN_TABS = ("資料管理", "帳號與權限管理")
VALID_ROLES = frozenset(("coach", "shared_coach", "manager", "admin"))


def sidebar_pages(role):
    """依伺服端登入角色提供入口，未知角色不開放功能。"""
    if role not in VALID_ROLES:
        return []
    pages = ["每日執行登錄", "客戶管理", "購買及分期", "教練查詢"]
    if role in ("coach", "manager", "admin"):
        pages.append("排班管理")
    if role in ("manager", "admin"):
        pages.append("營運總覽")
    if role == "admin":
        pages.extend(["財務平台", "系統管理平台"])
    return pages


def _active_tabs(labels, key, render):
    # 只有選取分頁才呼叫原功能，避免隱藏分頁重複查詢及表單衝突。
    tabs = st.tabs(labels, key=key, on_change="rerun")
    for label, tab in zip(labels, tabs):
        if tab.open:
            with tab:
                render(label)


def render_daily_execution(me, usage_renderer, operation_renderer):
    if me.get("role") not in VALID_ROLES:
        st.warning("您沒有此功能的使用權限。")
        return
    st.header("每日執行登錄")

    def render(label):
        if label == "銷課登錄":
            usage_renderer(me)
        else:
            operation_renderer(me, label)

    _active_tabs(DAILY_TABS, "daily_execution_tab", render)


def _admin_platform(me, title, labels, key, renderers):
    # 不僅隱藏選單；直接呼叫或偽造分頁也不得執行管理員功能。
    if me.get("role") != "admin":
        st.warning("此功能僅限系統管理員使用。")
        return
    st.header(title)
    _active_tabs(labels, key, lambda label: renderers[label](me))


def render_finance_platform(me, queries_renderer, monthly_renderer):
    _admin_platform(me, "財務平台", FINANCE_TABS, "finance_platform_tab",
                    dict(zip(FINANCE_TABS, (queries_renderer, monthly_renderer))))


def render_system_admin_platform(me, data_renderer, accounts_renderer):
    _admin_platform(me, "系統管理平台", ADMIN_TABS, "system_admin_platform_tab",
                    dict(zip(ADMIN_TABS, (data_renderer, accounts_renderer))))
