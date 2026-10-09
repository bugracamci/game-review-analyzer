"""About & Community: why this exists, who built it, contributors and a contact form."""
import streamlit as st

import config
from core import repo
from ui.auth import auth_configured
from ui.data import db

user = st.session_state.get("user")
owner = {**config.DEFAULT_OWNER, **(repo.get_setting(db(), "owner", {}) or {})}

st.title("About & Community")

st.markdown(f"""
### Why {config.APP_NAME} exists
Big studios have analysts and paid tools to read thousands of player reviews.
Small and indie teams usually don't – yet the reviews of the games you compete with are the
cheapest player research there is.

{config.APP_NAME} is a **free, non-profit community tool**: anyone can add a Google Play game,
an AI labels its reviews (sentiment, topics, feature requests), and every analysis joins a
**shared catalog** the next team can build on. You bring your own free AI key, so it costs
nobody anything.
""")

c1, c2, c3 = st.columns(3)
s = repo.stats(db())
c1.metric("Games in the catalog", s["games"])
c2.metric("Reviews analyzed", f"{s['labels']:,}")
c3.metric("Members", s["users"])

st.subheader("Who built this")
with st.container(border=True):
    st.markdown(f"**{owner['owner_name']}**  \n{owner['owner_role']}")
    links = [("LinkedIn", owner.get("owner_linkedin")), ("GitHub", owner.get("owner_github"))]
    cols = st.columns(4)
    for col, (label, url) in zip(cols, [x for x in links if x[1]]):
        col.link_button(label, url)
    st.caption("I'm building tools for small game teams and would love to hear what you're "
               "working on – use the form below, or connect on LinkedIn.")

st.subheader("How it works")
st.markdown("""
1. **Pick or add games** – paste any Google Play link. The newest reviews are downloaded.
2. **AI labels every review** – in batches, with your own Gemini key: sentiment (from the text,
   not the stars), 1–3 topics and a short feature-request summary.
3. **Compare** – sentiment, topics, trends by app version, real quotes and an AI brief
   for LiveOps, UA and game design.
4. **Take the data with you** – CSV, Excel or JSON.
""")

members = repo.community_members(db())
st.subheader("Community members")
if members.empty:
    st.caption("Be the first: turn on *Show me on the Community page* in Settings → Profile.")
else:
    for _, m in members.iterrows():
        name = m["name"] or "Member"
        label = f"[{name}]({m['profile_link']})" if m.get("profile_link") else name
        st.markdown(f"- {label} · {int(m['games_added'])} games added")
    st.caption("Shown only for members who opted in (Settings → Profile).")

st.subheader("Say hello, request a game or report a bug")
if not user:
    st.caption("Sign in (free) to send a message – so I can reply to you.")
    if auth_configured() and st.button("Sign in with Google"):
        st.login("google")
else:
    with st.form("contact", clear_on_submit=True):
        kind = st.selectbox("Topic", ["hello", "game_request", "idea", "bug"],
                            format_func={"hello": "👋 Just saying hello / let's connect",
                                         "game_request": "🎮 Please add a game",
                                         "idea": "💡 Feature idea",
                                         "bug": "🐞 Something is broken"}.get)
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
