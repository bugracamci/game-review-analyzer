"""Game Review Radar - Streamlit entry point.

Run locally:  streamlit run app.py
"""
import streamlit as st

import config
from ui.auth import current_user, is_admin, sidebar_account
from ui.data import sidebar_selectors

st.set_page_config(page_title=config.APP_NAME, page_icon="📡", layout="wide")

user = current_user()
st.session_state["user"] = user

sections = {
    "Analyze": [
        st.Page("pages/overview.py", title="Overview", icon="📊", default=True),
        st.Page("pages/trends.py", title="Trends", icon="📈"),
        st.Page("pages/explorer.py", title="Review Explorer", icon="🔎"),
        st.Page("pages/insights.py", title="Insights", icon="💡"),
    ],
    "Catalog": [
        st.Page("pages/catalog.py", title="Game Catalog", icon="🗂️"),
        st.Page("pages/add_game.py", title="Add a Game", icon="➕"),
        st.Page("pages/comparisons.py", title="My Comparisons & Export", icon="📁"),
    ],
    "You": [
        st.Page("pages/settings.py", title="Settings", icon="⚙️"),
        st.Page("pages/community.py", title="About & Community", icon="🤝"),
    ],
}
if is_admin(user):
    sections["Admin"] = [st.Page("pages/admin.py", title="Admin", icon="🛡️")]

page = st.navigation(sections)

st.sidebar.markdown(f"### 📡 {config.APP_NAME}")
st.sidebar.caption(config.APP_TAGLINE)
sidebar_account(user)
st.sidebar.divider()
sidebar_selectors(user)

page.run()
