"""原生字級、主標題及業務邏輯隔離驗證，不連線正式資料庫。"""
import ast
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
from ui_text import section_heading

MAIN={"每日執行登錄","客戶管理","購買及分期","教練查詢","營運總覽","財務平台","系統管理平台"}
SCRIPT="""
import streamlit as st
from ui_text import section_heading
from navigation_platforms import render_finance_platform, render_system_admin_platform, render_daily_execution
me={"role":st.session_state.get("role","admin")}
view=st.session_state.get("view","finance")
if view=="finance":
 render_finance_platform(me,lambda _:section_heading("各項查詢"),lambda _:section_heading("每月查詢"))
elif view=="system":
 render_system_admin_platform(me,lambda _:section_heading("資料管理"),lambda _:section_heading("帳號與權限管理"))
else:
 render_daily_execution(me,lambda _:section_heading("銷課登錄"),
                        lambda _,label:section_heading(label))
"""

class CanonicalTitles(ast.NodeTransformer):
    def visit_Constant(self,node):
        if node.value=="v1.13.11":
            node.value="v1.13.12"
        return node

    def visit_Call(self,node):
        self.generic_visit(node)
        if isinstance(node.func,ast.Name) and node.func.id=="section_heading":
            node.func=ast.Name(id="UI_TITLE",ctx=ast.Load())
            return node
        if not (isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
                and node.func.value.id=="st"):
            return node
        label=node.args[0].value if node.args and isinstance(node.args[0],ast.Constant) else None
        if node.func.attr=="subheader" or (node.func.attr=="header" and label not in MAIN):
            node.func=ast.Name(id="UI_TITLE",ctx=ast.Load())
            return node
        if node.func.attr=="markdown" and isinstance(label,str):
            match=re.fullmatch(r"#{1,6} (.+)",label)
            if match or (label.startswith("**") and label.endswith("**")):
                node.func=ast.Name(id="UI_TITLE",ctx=ast.Load())
                node.args=[ast.Constant(value=match.group(1) if match else label[2:-2])]
            elif label.startswith('<div style="font-size:1.5rem') and "上課預約取消" in label:
                node.func=ast.Name(id="UI_TITLE",ctx=ast.Load())
                node.args=[ast.Constant(value="上課預約取消")]
                node.keywords=[ast.keyword(arg="note",value=ast.Constant(value="（前一日及當日臨時請假者）"))]
        return node


class TypographyTests(unittest.TestCase):
    def app(self,view="finance",role="admin"):
        app=AppTest.from_string(SCRIPT,default_timeout=20)
        app.session_state["view"]=view
        app.session_state["role"]=role
        app.run()
        self.assertEqual(len(app.exception),0)
        return app

    def test_section_heading_uses_native_small_and_no_html(self):
        with patch("ui_text.st.markdown") as render:
            section_heading("各項查詢")
            self.assertEqual(render.call_args.args,(":small[**各項查詢**]",))
            self.assertFalse(render.call_args.kwargs.get("unsafe_allow_html",False))

    def test_note_uses_same_small_size(self):
        with patch("ui_text.st.markdown") as render:
            section_heading("上課預約取消","（前一日及當日臨時請假者）")
            self.assertEqual(render.call_args.args,
                (":small[**上課預約取消** （前一日及當日臨時請假者）]",))

    def test_special_text_is_escaped(self):
        with patch("ui_text.st.markdown") as render:
            section_heading("[文字](網址)_*<tag>")
            self.assertEqual(render.call_args.args,
                (r":small[**\[文字\](網址)\_\*\<tag\>**]",))

    def test_financial_title_stays_large_and_children_use_tab_size(self):
        app=self.app()
        self.assertEqual([x.value for x in app.header],["財務平台"])
        self.assertEqual([x.value for x in app.markdown],[":small[**各項查詢**]"])
        app.session_state["finance_platform_tab"]="每月查詢"
        app.run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual([x.value for x in app.header],["財務平台"])
        self.assertEqual([x.value for x in app.markdown],[":small[**每月查詢**]"])

    def test_management_title_and_subsections(self):
        app=self.app("system")
        self.assertEqual([x.value for x in app.header],["系統管理平台"])
        self.assertEqual([x.value for x in app.markdown],[":small[**資料管理**]"])
        app.session_state["system_admin_platform_tab"]="帳號與權限管理"
        app.run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual([x.value for x in app.markdown],[":small[**帳號與權限管理**]"])

    def test_daily_title_and_registration(self):
        app=self.app("daily","coach")
        self.assertEqual([x.value for x in app.header],["每日執行登錄"])
        self.assertEqual([x.value for x in app.markdown],[":small[**銷課登錄**]"])

    def test_guard_still_prevents_admin_platform_access(self):
        for view in ("finance","system"):
            app=self.app(view,"coach")
            self.assertEqual(len(app.warning),1)
            self.assertEqual(len(app.header),0)
            self.assertEqual(len(app.markdown),0)

    def test_formal_business_functions_are_unchanged_except_titles_version(self):
        previous=ROOT/"output/release_v1.13.11/app.py"
        latest=ROOT/"output/release_v1.13.12/app.py"
        if not previous.exists():
            self.skipTest("未附歷史快照；發布工作區完成此比較。")
        if not latest.exists():
            latest=ROOT/"app.py"
        old=CanonicalTitles().visit(ast.parse(previous.read_text(encoding="utf-8")))
        new=CanonicalTitles().visit(ast.parse(latest.read_text(encoding="utf-8")))
        functions=lambda tree:{n.name:ast.dump(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(functions(old),functions(new))
        old_nav=(ROOT/"output/release_v1.13.11/navigation_platforms.py").read_text(encoding="utf-8")
        self.assertEqual(old_nav,(ROOT/"navigation_platforms.py").read_text(encoding="utf-8"))

    def test_formal_has_only_sidebar_main_headers_and_no_big_subheads(self):
        latest=ROOT/"output/release_v1.13.13/app.py"
        if not latest.exists(): latest=ROOT/"app.py"
        source=latest.read_text(encoding="utf-8")
        tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                if node.func.value.id=="st" and node.func.attr=="header":
                    self.assertIn(node.args[0].value,MAIN)
                if node.func.value.id=="st":
                    self.assertNotEqual(node.func.attr,"subheader")
        self.assertNotIn("font-size:1.5rem",source)
        self.assertGreaterEqual(source.count("section_heading("),45)
        self.assertEqual((ROOT/"VERSION").read_text().strip(),"v1.13.13")

if __name__=="__main__":
    unittest.main()
