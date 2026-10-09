"""Mobile Game Review Analyzer - Streamlit entry point.

Run locally:  streamlit run app.py
"""
import streamlit as st

from config import DB_PATH
from dashboard_data import load_reviews, sidebar_game_filter

st.set_page_config(page_title="Mobile Game Review Analyzer", page_icon="🎮", layout="wide")

if not DB_PATH.exists():
    st.error("No data yet. Run `python fetch_reviews.py` and `python classify_reviews.py` first.")
    st.stop()

reviews = load_reviews()
if reviews.empty:
    st.error("The database has no labeled reviews yet. Run `python classify_reviews.py`.")
    st.stop()

st.sidebar.title("🎮 Review Analyzer")
sidebar_game_filter(reviews)

page = st.navigation([
    st.Page("pages/overview.py", title="Overview", icon="📊", default=True),
    st.Page("pages/trends.py", title="Trends", icon="📈"),
    st.Page("pages/explorer.py", title="Review Explorer", icon="🔎"),
    st.Page("pages/insights.py", title="Insights", icon="💡"),
])
st.sidebar.divider()
st.sidebar.caption(
    "Labels by an LLM (Gemini Flash) in batches of 25. "
    "This dashboard reads saved results only - no API calls."
)
page.run()
