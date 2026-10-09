"""Insights: the LLM-written brief for LiveOps and UA teams (generated offline)."""
import streamlit as st

from dashboard_data import load_latest_insights

st.title("Insights for LiveOps & UA")

ins = load_latest_insights()
if not ins:
    st.info("No insights yet. Run `python generate_insights.py` once.")
    st.stop()

st.caption(f"Written by {ins['model']} on {ins['created_at'][:10]} from "
           f"{ins.get('reviews_analyzed', '?')} labeled reviews. The numbers were computed with "
           "pandas; the model only interprets them. Always check before acting.")
st.info(f"**{ins.get('headline', '')}**")

st.subheader("Key findings")
for f in ins.get("key_findings", []):
    st.markdown(f"- **{f.get('finding', '')}**  \n  <small>{f.get('evidence', '')}</small>",
                unsafe_allow_html=True)

st.subheader("Game by game")
games = ins.get("games", [])
if games:
    for col, g in zip(st.columns(len(games)), games):
        with col.container(border=True):
            st.markdown(f"#### {g.get('game', '')}")
            for title, key in [("👍 Players love", "players_love"),
                               ("👎 Players complain about", "players_complain_about"),
                               ("💡 Top requests", "top_requests")]:
                st.markdown(f"**{title}**")
                for item in g.get(key, []):
                    st.markdown(f"- {item}")

left, right = st.columns(2)
with left:
    st.subheader("LiveOps actions")
    for a in ins.get("liveops_actions", []):
        st.markdown(f"- **{a.get('game', '')}:** {a.get('action', '')}  \n"
                    f"  <small>Why: {a.get('why', '')}</small>", unsafe_allow_html=True)
with right:
    st.subheader("UA / ad creative angles")
    for a in ins.get("ua_angles", []):
        st.markdown(f"- **{a.get('angle', '')}**  \n  <small>Why: {a.get('why', '')}</small>",
                    unsafe_allow_html=True)

st.subheader("Opportunities for a new survivor-like game")
for o in ins.get("new_game_opportunities", []):
    st.markdown(f"- {o}")
