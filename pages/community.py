"""About & Community: why this exists, who built it, contributors and a contact form."""
import streamlit as st

import config
from core import repo
from ui import theme
from ui.auth import auth_configured
from ui.data import db

user = st.session_state.get("user")
owner = {**config.DEFAULT_OWNER, **(repo.get_setting(db(), "owner", {}) or {})}

theme.page_header("Community", "Built for small game teams",
                  "Big studios have analysts and paid tools to read thousands of player reviews. "
                  "Small and indie teams usually don't – yet the reviews of the games you compete "
                  "with are the cheapest player research there is.")

s = repo.stats(db())
theme.kpis([("Games in the catalog", f"{s['games']:,}"), ("Reviews analyzed", f"{s['labels']:,}"),
            ("Members", f"{s['users']:,}")])

left, right = st.columns([3, 2], gap="medium")
with left:
    theme.section("How it works")
    steps = [("Pick or add games", "Paste any Google Play link. The newest reviews are downloaded."),
             ("AI labels every review", "With your own free Gemini key: sentiment from the text "
              "(not the stars), 1–3 topics and a short feature-request summary."),
             ("Compare", "Sentiment, topics, trends by app version, real quotes and an AI brief "
              "for LiveOps, UA and game design."),
             ("Take the data with you", "CSV, Excel or JSON – it's your research.")]
    theme.html("".join(
        f'<div style="display:flex;gap:14px;padding:12px 0;border-bottom:1px solid {theme.BORDER}">'
        f'<span class="mono" style="color:{theme.ACCENT};font-weight:700">{i:02d}</span>'
        f'<div><div style="font-weight:600;color:{theme.INK}">{theme.esc(t)}</div>'
        f'<div style="color:{theme.INK_2};font-size:14px;margin-top:2px;line-height:1.5">{theme.esc(d)}</div></div></div>'
        for i, (t, d) in enumerate(steps, 1)))
    theme.html(f'<p class="gr-sub" style="font-size:14px">{theme.esc(config.APP_NAME)} is a '
               f'<b style="color:{theme.INK}">free, non-profit community tool</b>. Every analysis '
               f'joins a shared catalog the next team can build on.</p>')

with right:
    theme.section("Who built this")
    with st.container(border=True):
        theme.html(f'<div style="display:flex;gap:14px;align-items:center">'
                   f'{theme.tile(owner["owner_name"], theme.ACCENT, 52)}'
                   f'<div><div style="font-family:Sora,sans-serif;font-weight:600;font-size:18px">'
                   f'{theme.esc(owner["owner_name"])}</div>'
                   f'<div style="color:{theme.MUTED};font-size:14px">{theme.esc(owner["owner_role"])}</div>'
                   f'</div></div><p style="color:{theme.INK_2};font-size:14px;line-height:1.55;margin:14px 0 4px">'
                   f"I'm building tools for small game teams and would love to hear what you're "
                   f"working on – use the form below, or connect on LinkedIn.</p>")
        links = [(lbl, url, icon) for lbl, url, icon in
                 [("LinkedIn", owner.get("owner_linkedin"), ":material/person_add:"),
                  ("GitHub", owner.get("owner_github"), ":material/code:")] if url]
        for col, (lbl, url, icon) in zip(st.columns(max(len(links), 1)), links):
            col.link_button(lbl, url, icon=icon, width="stretch",
                            type="primary" if lbl == "LinkedIn" else "secondary")

    members = repo.community_members(db())
    theme.section("Community members")
    if members.empty:
        st.caption("Be the first: turn on *Show me on the Community page* in Settings → Profile.")
    else:
        rows = []
        for _, m in members.iterrows():
            name = theme.esc(m["name"] or "Member")
            if m.get("profile_link"):
                name = f'<a href="{theme.esc(m["profile_link"])}" target="_blank" rel="noopener">{name}</a>'
            rows.append(f'<div style="display:flex;justify-content:space-between;padding:8px 0;'
                        f'border-bottom:1px solid {theme.BORDER}"><span>{name}</span>'
                        f'<span class="mono" style="color:{theme.MUTED};font-size:13px">'
                        f'{int(m["games_added"])} games</span></div>')
        theme.html("".join(rows))
        st.caption("Shown only for members who opted in (Settings → Profile).")

theme.section("Say hello, request a game or report a bug")
if not user:
    st.caption("Sign in (free) to send a message – so I can reply to you.")
    if auth_configured() and st.button("Sign in with Google", type="primary"):
        st.login("google")
else:
    with st.form("contact", clear_on_submit=True):
        kind = st.selectbox("Topic", ["hello", "game_request", "idea", "bug"],
                            format_func={"hello": "Just saying hello / let's connect",
                                         "game_request": "Please add a game",
                                         "idea": "Feature idea",
                                         "bug": "Something is broken"}.get)
        message = st.text_area("Message", max_chars=2000,
                               placeholder="What are you building? What would help your team?")
        if st.form_submit_button("Send", type="primary") and message.strip():
            repo.add_feedback(db(), user["email"], user.get("display_name") or user.get("name"),
                              kind, message.strip())
            st.success("Thanks! Your message reached the admin inbox. "
                       f"I'll reply to {user['email']}.")

st.divider()
st.caption("Reviews come from public Google Play pages via the open-source google-play-scraper "
           "package; no reviewer names are stored. Labels are AI estimates – check the quotes "
           "before acting. Source code: "
           "[GitHub](https://github.com/bugracamci/game-review-analyzer).")
