"""Insights: an AI-written brief for LiveOps, UA and game design (cached per game set)."""
from html import escape

import streamlit as st

from core import repo
from ui import actions
from ui.components import analysis_data
from ui.data import db, selected_ids

user, df, scheme = analysis_data(
    "Insights for LiveOps, UA & game design",
    "An AI brief for the games selected in the sidebar. Numbers come from pandas; "
    "the model only interprets them.")

ids = selected_ids()
key = repo.scope_key(ids, scheme["id"])
ins = repo.latest_insight(db(), key)

if user:
    label = "Regenerate with my API key" if ins else "Write the brief with my API key"
    if st.button(label, type="secondary" if ins else "primary"):
        if actions.run_insights(user, ids, scheme["id"]):
            st.rerun()
if not ins:
    st.info("No brief for this exact set of games yet. "
            + ("Click the button above – it takes one AI request."
               if user else "Sign in (free) to write one with your own Gemini key."))
    st.stop()

missing = set(df["game"].unique()) - set(ins.get("games_compared", []))
st.caption(f"Written by {ins['model']} on {ins['created_at'][:10]} from "
           f"{ins.get('reviews_analyzed', '?')} labeled reviews. Always double-check before acting.")
if missing:
    st.warning("This brief was written before some data was added – regenerate it for fresh results.")
st.info(f"**{ins.get('headline', '')}**")

st.subheader("Key findings")
for f in ins.get("key_findings", []):
    st.markdown(f"- **{escape(f.get('finding', ''))}**  \n  <small>{escape(f.get('evidence', ''))}</small>",
                unsafe_allow_html=True)

st.subheader("Game by game")
games = ins.get("games", [])
for start in range(0, len(games), 4):
    for col, g in zip(st.columns(4), games[start:start + 4]):
        with col.container(border=True):
            st.markdown(f"#### {g.get('game', '')}")
            for title, k in [("👍 Players love", "players_love"),
                             ("👎 Players complain about", "players_complain_about"),
                             ("💡 Top requests", "top_requests")]:
                st.markdown(f"**{title}**")
                for item in g.get(k, []):
                    st.markdown(f"- {item}")

left, right = st.columns(2)
with left:
    st.subheader("LiveOps actions")
    for a in ins.get("liveops_actions", []):
        st.markdown(f"- **{escape(a.get('game', ''))}:** {escape(a.get('action', ''))}  \n"
                    f"  <small>Why: {escape(a.get('why', ''))}</small>", unsafe_allow_html=True)
with right:
    st.subheader("UA / ad creative angles")
    for a in ins.get("ua_angles", []):
        st.markdown(f"- **{escape(a.get('angle', ''))}**  \n  <small>Why: {escape(a.get('why', ''))}</small>",
                    unsafe_allow_html=True)

st.subheader("Opportunities for a new game in this genre")
for o in ins.get("new_game_opportunities", []):
    st.markdown(f"- {o}")
