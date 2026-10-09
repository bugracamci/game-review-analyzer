"""Game Review Radar - Streamlit entry point.

Run locally:  streamlit run app.py
"""
import importlib
import os
import sys

import streamlit as st

import config

# Dev mode only: reload ui/ modules when their files change. Streamlit re-runs page files on
# every rerun but keeps imported modules cached, so theme edits would otherwise need a restart.
if os.environ.get("DEV_LOGIN_EMAIL"):
    _ui = [m for m in ("config", "ui.theme", "ui.auth", "ui.data", "ui.components", "ui.actions")
           if m in sys.modules]
    if any(os.path.getmtime(sys.modules[m].__file__) != getattr(sys.modules[m], "_mtime", None)
           for m in _ui):
        for m in _ui:
            importlib.reload(sys.modules[m])
            sys.modules[m]._mtime = os.path.getmtime(sys.modules[m].__file__)

from ui import theme
from ui.auth import current_user, is_admin, sidebar_account
from ui.data import sidebar_selectors

st.set_page_config(page_title=config.APP_NAME, page_icon="assets/icon.svg", layout="wide")
theme.apply()
st.logo("assets/logo.svg", icon_image="assets/icon.svg", size="large")

user = current_user()
st.session_state["user"] = user

sections = {
    "Analyze": [
        st.Page("pages/overview.py", title="Overview", icon=":material/space_dashboard:", default=True),
        st.Page("pages/trends.py", title="Trends", icon=":material/trending_up:"),
        st.Page("pages/impact.py", title="Before / after", icon=":material/compare_arrows:"),
        st.Page("pages/explorer.py", title="Reviews", icon=":material/forum:"),
        st.Page("pages/insights.py", title="Insights", icon=":material/lightbulb:"),
    ],
    "Catalog": [
        st.Page("pages/catalog.py", title="All games", icon=":material/grid_view:"),
        st.Page("pages/add_game.py", title="Add a game", icon=":material/add_circle:"),
        st.Page("pages/comparisons.py", title="Saved & export", icon=":material/folder_open:"),
    ],
    "You": [
        st.Page("pages/settings.py", title="Settings", icon=":material/tune:"),
        st.Page("pages/community.py", title="Community", icon=":material/group:"),
    ],
}
if is_admin(user):
    sections["Admin"] = [st.Page("pages/admin.py", title="Admin", icon=":material/shield_person:")]

page = st.navigation(sections)

sidebar_selectors(user)
st.sidebar.divider()
sidebar_account(user)

page.run()
