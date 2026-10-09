"""Add a Game: paste a Google Play link (or search), then download + label its reviews."""
import streamlit as st

import config
from core import fetcher, limits, repo
from ui import actions
from ui.auth import is_admin, require_login
from ui.data import db, select_games, selected_ids, user_api_key, user_prefs

user = st.session_state.get("user")
st.title("Add a game")
st.caption("Any Google Play game. Its reviews are downloaded, labeled with your own API key "
           "and added to the shared catalog, so the whole community can compare it.")
require_login(user, "add games")

prefs = user_prefs(user)
ok, remaining = limits.check(db(), user["email"], "new_games_per_day", is_admin(user))
has_key = bool(user_api_key(user, prefs["provider"]))
c1, c2 = st.columns(2)
c1.metric("New games you can add today", "∞" if is_admin(user) else remaining)
c2.metric("API key", "✅ ready" if has_key else "❌ missing")
if not has_key:
    st.warning(actions.NO_KEY_MSG)

# --- 1. Find the game -------------------------------------------------------------
st.subheader("1 · Find the game")
tab_link, tab_search = st.tabs(["Paste a Google Play link", "Search by name"])
with tab_link:
    link = st.text_input("Google Play link or package name",
                         placeholder="https://play.google.com/store/apps/details?id=com.example.game")
    if st.button("Find game") and link:
        app_id = fetcher.parse_app_id(link)
        if app_id:
            st.session_state["add_candidate"] = app_id
        else:
            st.error("That doesn't look like a Google Play link or package name.")
with tab_search:
    term = st.text_input("Game name", placeholder="e.g. Magic Survival")
    if st.button("Search") and term.strip():
        try:
            st.session_state["add_results"] = fetcher.search_games(term.strip())
        except Exception as e:  # noqa: BLE001
            st.error(f"Search failed: {e}")
    for r in st.session_state.get("add_results", []):
        cols = st.columns([1, 6, 2])
        if r.get("icon_url"):
            cols[0].image(r["icon_url"], width=40)
        cols[1].markdown(f"**{r['name']}**  \n<small>{r.get('developer') or ''} · "
                         f"{r.get('genre') or ''} · `{r['app_id']}`</small>",
                         unsafe_allow_html=True)
        if cols[2].button("Choose", key=f"pick_{r['app_id']}"):
            st.session_state["add_candidate"] = r["app_id"]
    if st.session_state.get("add_results"):
        st.caption("Tip: check the developer – Google Play search shows many copycat games.")

app_id = st.session_state.get("add_candidate")
if not app_id:
    st.stop()


@st.cache_data(ttl=3600, show_spinner="Looking up the game…")
def _lookup(app_id: str):
    return fetcher.lookup_game(app_id)


try:
    game = _lookup(app_id)
except ValueError as e:
    st.error(str(e))
    st.stop()

# --- 2. Confirm ---------------------------------------------------------------------
st.subheader("2 · Check it's the right game")
with st.container(border=True):
    cols = st.columns([1, 6])
    if game.get("icon_url"):
        cols[0].image(game["icon_url"], width=72)
    rating = f"{game['avg_rating']:.1f}★" if game.get("avg_rating") else "no rating"
    cols[1].markdown(f"### {game['name']}\n{game.get('developer')} · {game.get('genre')} · "
                     f"{game.get('installs')} installs · {rating}")
existing = repo.get_game(db(), app_id)
if existing and not existing.get("is_hidden"):
    st.info("This game is already in the catalog. You can compare it right away, "
            "or download its newest reviews below.")
    if st.button("Compare it now"):
        select_games(list(dict.fromkeys(selected_ids() + [app_id])))
        st.session_state.pop("add_candidate", None)
        st.switch_page("pages/overview.py")
elif existing:
    st.warning("This game was removed from the catalog by the admin.")
    st.stop()

# --- 3. Options + run -----------------------------------------------------------------
st.subheader("3 · Download and analyze")
markets = {m[0]: m for m in config.MARKETS}
c1, c2 = st.columns(2)
market = c1.selectbox("Store country & language", list(markets),
                      index=list(markets).index(prefs.get("market", "us"))
                      if prefs.get("market", "us") in markets else 0,
                      format_func=lambda m: markets[m][2])
count = c2.slider("Newest reviews to download", 100, config.MAX_REVIEWS_PER_GAME,
                  int(prefs["reviews_per_game"]), step=100)
calls = -(-count // int(prefs["batch_size"]))
st.caption(f"≈ {calls} AI requests with your key ({prefs['model']}). Free Gemini keys have a "
           "daily request limit; if it runs out, labeling pauses and you can continue tomorrow "
           "from the Overview page. More than 400 reviews is best with a paid key.")

if not existing and not ok:
    st.warning("You've reached today's limit for new games. It resets within 24 hours.")
    st.stop()

if st.button("Add & analyze", type="primary", disabled=not has_key):
    country, lang = markets[market][0], markets[market][1]
    result = actions.run_collect(user, app_id, country, lang, count, is_new=not existing)
    if result:
        summary = actions.run_labeling(user, [app_id], config.DEFAULT_SCHEME_ID)
        select_games(list(dict.fromkeys(selected_ids() + [app_id])))
        st.session_state.pop("add_candidate", None)
        st.session_state.pop("add_results", None)
        if summary and not summary.get("stopped"):
            st.success(f"{game['name']} is in the catalog and selected for comparison.")
            st.balloons()
        st.page_link("pages/overview.py", label="Go to the comparison →", icon="📊")
