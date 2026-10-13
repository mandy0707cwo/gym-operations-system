"""原生頁內標題：字級跟隨分頁，保留主選單同名標題。"""
import streamlit as st

_MARKUP_ESCAPES = str.maketrans({char: "\\" + char for char in "\\*_[]<>" + chr(96)})


def section_heading(label, note=None):
    """使用 Streamlit 原生 small 字級（與 tabs label 相同），不用自訂 CSS。"""
    text = str(label).translate(_MARKUP_ESCAPES)
    suffix = " " + str(note).translate(_MARKUP_ESCAPES) if note else ""
    st.markdown(":small[**" + text + "**" + suffix + "]")
