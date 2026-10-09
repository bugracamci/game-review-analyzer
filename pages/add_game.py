"""Add a Game: paste a Google Play link (or search), then download + label its reviews."""
from html import escape

import streamlit as st

import config
from core import fetcher, limits, repo
from ui import theme
from ui import actions
from ui.auth import is_admin, require_login
from ui.components import fetch_options
from ui.data import db, select_games, selected_ids, user_api_key, user_prefs

user = st.session_state.get("user")
theme.page_header("Catalog", "Add a game",
                  "Any Google Play game. Its newest reviews are downloaded, labeled with your own "
                  "API key and added to the shared catalog for the whole community.")
require_login(user, "add games")

prefs = user_prefs(user)
ok, remaining = limits.check(db(), user["email"], "new_games_per_day", is_admin(user))
has_key = bool(user_api_key(user, prefs["provider"]))
theme.pills([("New games today", "unlimited" if is_admin(user) else f"{remaining} left",
              is_admin(user) or remaining > 0),
             ("API key", "ready" if has_key else "missing", has_key)])
if not has_key:
    st.warning(actions.NO_KEY_MSG)

# --- 1. Find the game -------------------------------------------------------------
theme.section("Find the game", 1)
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
        cols[1].markdown(f"**{escape(str(r['name']))}**  \n<small>"
                         f"{escape(str(r.get('developer') or ''))} · "
                         f"{escape(str(r.get('genre') or ''))} · {escape(r['app_id'])}</small>",
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
theme.section("Check it's the right game", 2,
              "Google Play is full of copycats – make sure the developer is right.")
rating = f"{game['avg_rating']:.1f}★" if game.get("avg_rating") else "no rating"
icon = (f'<img src="{theme.esc(game["icon_url"])}" alt="" width="72" height="72" style="border-radius:16px">'
        if game.get("icon_url") else theme.tile(game["name"], theme.GAME_COLORS[0], 72))
theme.html(f'<div class="gr-panel" style="padding:20px;display:flex;gap:18px;align-items:center">{icon}'
           f'<div style="flex:1;min-width:0"><div style="font-family:Sora,sans-serif;font-size:22px;'
           f'font-weight:600">{theme.esc(game["name"])}</div>'
           f'<div style="color:{theme.MUTED};font-size:14px;margin-top:4px">'
           f'{theme.esc(game.get("developer") or "")} · {theme.esc(game.get("genre") or "")} · '
           f'{theme.esc(str(game.get("installs") or "?"))} installs · '
           f'<span class="mono">{theme.esc(app_id)}</span></div></div>'
           f'<span class="mono" style="font-size:20px;font-weight:700">{rating}</span></div>')
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
theme.section("Download and analyze", 3)
markets = {m[0]: m for m in config.MARKETS}
market = st.selectbox("Store country & language", list(markets),
                      index=list(markets).index(prefs.get("market", "us"))
                      if prefs.get("market", "us") in markets else 0,
                      format_func=lambda m: markets[m][2])
opts = fetch_options("add", bool(existing), int(prefs["reviews_per_game"]), int(prefs["batch_size"]))

if not existing and not ok:
    st.warning("You've reached today's limit for new games. It resets within 24 hours.")
    st.stop()

if st.button("Add & analyze" if not existing else "Download & analyze", type="primary",
             disabled=not has_key or opts is None):
    country, lang = markets[market][0], markets[market][1]
    result = actions.run_collect(user, app_id, country, lang, opts["count"], is_new=not existing,
                                 mode=opts["mode"], start=opts["start"], end=opts["end"],
                                 version=opts["version"])
    if result:
        summary = actions.run_labeling(user, [app_id], config.DEFAULT_SCHEME_ID)
        select_games(list(dict.fromkeys(selected_ids() + [app_id])))
        st.session_state.pop("add_candidate", None)
        st.session_state.pop("add_results", None)
        if summary and not summary.get("stopped"):
            st.success(f"{game['name']} is in the catalog and selected for comparison.")
        st.page_link("pages/overview.py", label="Go to the comparison",
                     icon=":material/arrow_forward:")
