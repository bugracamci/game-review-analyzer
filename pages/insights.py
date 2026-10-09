"""Insights: an AI-written brief for LiveOps, UA and game design (cached per game set)."""
from html import escape

import streamlit as st

from core import repo
from ui import actions, theme
from ui.components import analysis_data
from ui.data import active_filters, db, selected_ids

user, df, scheme = analysis_data(
    "Insights for LiveOps, UA & game design",
    "An AI brief for the games selected in the sidebar. Numbers come from pandas; "
    "the model only interprets them.", filtered=False)

ids = selected_ids()
key = repo.scope_key(ids, scheme["id"])
ins = repo.latest_insight(db(), key)

if active_filters():
    st.caption("The brief always covers all labeled reviews – sidebar filters don't apply here.")
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
E = theme.esc
st.caption(f"Written by {ins['model']} on {ins['created_at'][:10]} from "
           f"{ins.get('reviews_analyzed', '?')} labeled reviews. Always double-check before acting.")
if missing:
    st.warning("This brief was written before some data was added – regenerate it for fresh results.")

theme.html(f'<div class="gr-panel" style="padding:28px;display:flex;gap:18px;align-items:flex-start;'
           f'border-color:#24543A;background:#0F1C17;margin:6px 0 10px">'
           f'<span class="gr-label" style="color:{theme.ACCENT};white-space:nowrap;padding-top:6px">Headline</span>'
           f'<p style="margin:0;font-family:Sora,sans-serif;font-size:24px;line-height:1.4;font-weight:500;'
           f'color:{theme.INK}">{E(ins.get("headline", ""))}</p></div>')

st.markdown('<h2 class="gr-h2">Key findings</h2>', unsafe_allow_html=True)
findings = ins.get("key_findings", [])
per_row = 2 if len(findings) in (2, 4) else 3  # avoid a lonely card on the last row
for start in range(0, len(findings), per_row):
    for i, (col, f) in enumerate(zip(st.columns(per_row), findings[start:start + per_row]),
                                 start=start + 1):
        with col:
            theme.html(f'<div class="gr-panel" style="padding:20px;height:100%;box-sizing:border-box">'
                       f'<span class="mono" style="color:{theme.ACCENT};font-weight:700">{i:02d}</span>'
                       f'<div style="font-weight:600;font-size:16px;margin:8px 0 6px;line-height:1.4">{E(f.get("finding", ""))}</div>'
                       f'<div style="font-size:14px;color:{theme.INK_2};line-height:1.5">{E(f.get("evidence", ""))}</div></div>')

st.markdown('<h2 class="gr-h2" style="margin-top:12px">Game by game</h2>', unsafe_allow_html=True)
games = ins.get("games", [])
for start in range(0, len(games), 4):
    for col, g in zip(st.columns(4), games[start:start + 4]):
        parts = ""
        for title, k, color in [("Players love", "players_love", theme.POS),
                                ("Complaints", "players_complain_about", theme.NEG_TEXT),
                                ("Top requests", "top_requests", theme.AMBER)]:
            items = "".join(f"<li>{E(x)}</li>" for x in g.get(k, []))
            parts += (f'<div style="margin-top:12px"><span class="gr-label" style="color:{color}">{title}</span>'
                      f'<ul style="margin:6px 0 0;padding-left:18px;font-size:14px;line-height:1.5;color:{theme.INK}">{items}</ul></div>')
        with col:
            theme.html(f'<div class="gr-panel" style="padding:20px;height:100%;box-sizing:border-box">'
                       f'<div style="font-family:Sora,sans-serif;font-weight:600;font-size:17px">{E(g.get("game", ""))}</div>{parts}</div>')

left, right = st.columns(2)
with left:
    items = "".join(f'<li style="margin-bottom:14px"><span class="gr-chip" style="margin-bottom:6px">{E(a.get("game", ""))}</span>'
                    f'<div style="font-weight:600;margin-top:6px">{E(a.get("action", ""))}</div>'
                    f'<div style="font-size:14px;color:{theme.INK_2}">{E(a.get("why", ""))}</div></li>'
                    for a in ins.get("liveops_actions", []))
    theme.html(f'<div class="gr-panel" style="padding:24px;margin-top:12px"><h2 class="gr-h2">LiveOps actions</h2>'
               f'<ol style="list-style:none;margin:16px 0 0;padding:0">{items}</ol></div>')
with right:
    items = "".join(f'<li style="margin-bottom:14px"><div style="font-weight:600">{E(a.get("angle", ""))}</div>'
                    f'<div style="font-size:14px;color:{theme.INK_2}">{E(a.get("why", ""))}</div></li>'
                    for a in ins.get("ua_angles", []))
    theme.html(f'<div class="gr-panel" style="padding:24px;margin-top:12px"><h2 class="gr-h2">UA &amp; ad creative angles</h2>'
               f'<ol style="list-style:none;margin:16px 0 0;padding:0">{items}</ol></div>')

opps = "".join(f"<li>{E(o)}</li>" for o in ins.get("new_game_opportunities", []))
if opps:
    theme.html(f'<div class="gr-panel" style="padding:24px;margin-top:12px;border-color:#5A4520;background:#17140C">'
               f'<h2 class="gr-h2" style="color:{theme.AMBER}">Opportunities for a new game in this genre</h2>'
               f'<ul style="margin:12px 0 0;padding-left:20px;line-height:1.6;color:#E8DCC0">{opps}</ul></div>')
