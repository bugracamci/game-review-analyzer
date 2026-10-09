"""All games: every game the community has analyzed. Pick games to compare."""
import pandas as pd
import streamlit as st

import config
from core import repo
from ui import actions, theme
from ui.components import fetch_options
from ui.data import db, games_table, select_games, selected_ids

user = st.session_state.get("user")
games = games_table()
theme.page_header(f"{len(games)} games · {int(games['n_labeled'].sum()) if not games.empty else 0:,} "
                  "labeled reviews", "Game catalog",
                  "Every game analyzed by the community. Pick games to compare them.")
if games.empty:
    st.info("No games yet. Add the first one on **Add a game**.")
    st.stop()

# --- Download job: options in a dialog, the run itself happens here in full view -------------
@st.dialog("Download reviews", width="large")
def download_dialog(app_id: str, name: str, have: int) -> None:
    from ui.data import user_prefs
    prefs = user_prefs(user)
    st.markdown(f"**{name}** · {have:,} reviews stored")
    opts = fetch_options(f"dl_{app_id}", True, int(prefs["reviews_per_game"]),
                         int(prefs["batch_size"]))
    if st.button("Download & analyze", type="primary", disabled=opts is None, width="stretch"):
        st.session_state["_catalog_job"] = {"app_id": app_id, **opts}
        st.rerun()


if user and "_dl_open" in st.session_state:
    download_dialog(*st.session_state.pop("_dl_open"))

job = st.session_state.pop("_catalog_job", None)
if job and user:
    country, lang = repo.main_market(db(), job["app_id"])
    r = actions.run_collect(user, job["app_id"], country, lang, job["count"], is_new=False,
                            mode=job["mode"], start=job["start"], end=job["end"],
                            version=job["version"])
    if r is not None:
        reasons = {"reached stored reviews": "reached reviews we already had",
                   "passed the start date": "passed the start date",
                   "passed the version": "passed that version",
                   "version not found": "that version wasn't found",
                   "end of reviews": "reached the oldest review on Google Play",
                   "got enough": "got the number you asked for",
                   "read limit reached": "hit the read limit for one download"}
        st.caption(f"Read {r['pages'] * 200:,} reviews"
                   + (f", back to {r['oldest']:%d %b %Y}" if r.get("oldest") else "")
                   + f" · stopped because it {reasons.get(r['stop'], r['stop'])}.")
        if r["added"]:
            actions.run_labeling(user, [job["app_id"]], config.DEFAULT_SCHEME_ID)
            st.success(f"{r['game']['name']}: {r['added']:,} reviews added. Every analysis page "
                       "now includes them (check the date filter in the sidebar).")
        else:
            st.info(f"{r['game']['name']}: no reviews matched that we don't already have.")
    games = games_table()

c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
query = c1.text_input("Search", placeholder="Game, developer or genre")
genres = sorted(g for g in games["genre"].dropna().unique())
genre = c2.segmented_control("Genre", ["All"] + genres, default="All") or "All"
sort = c3.selectbox("Sort", ["Most reviews", "Recently updated", "Store rating", "Name"])

view = games.copy()
if query.strip():
    q = query.strip().lower()
    view = view[view[["name", "developer", "genre"]].fillna("").apply(
        lambda r: q in " ".join(r).lower(), axis=1)]
if genre != "All":
    view = view[view["genre"] == genre]
view = {"Name": view.sort_values("name"),
        "Most reviews": view.sort_values("n_reviews", ascending=False),
        "Recently updated": view.sort_values("last_fetched_at", ascending=False),
        "Store rating": view.sort_values("avg_rating", ascending=False)}[sort]

chosen = selected_ids()
if chosen:
    with st.container(border=True):
        a, b = st.columns([4, 1], vertical_alignment="center")
        a.markdown(f"**{len(chosen)} selected** for comparison")
        if b.button("Compare now", type="primary", width="stretch"):
            st.switch_page("pages/overview.py")


def toggle(app_id: str) -> None:
    ids = [a for a in selected_ids() if a != app_id]
    if app_id not in selected_ids():
        ids.append(app_id)
    select_games(ids)


for start in range(0, len(view), 3):
    for col, (_, g) in zip(st.columns(3), view.iloc[start:start + 3].iterrows()):
        with col.container(border=True):
            icon = (f'<img src="{theme.esc(g["icon_url"])}" alt="" width="56" height="56" '
                    f'style="border-radius:14px;flex:none">' if g.get("icon_url")
                    else theme.tile(g["name"], theme.GAME_COLORS[0], 56))
            rating = f"{g['avg_rating']:.1f}★" if pd.notna(g.get("avg_rating")) else "–"
            labeled_share = g["n_labeled"] / g["n_reviews"] if g["n_reviews"] else 0
            by = (f" · added by {theme.esc(g['added_by_name'])}"
                  if g.get("added_by_public") and g.get("added_by_name") else "")
            theme.html(
                f'<div style="display:flex;gap:14px;align-items:flex-start">{icon}'
                f'<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:17px">{theme.esc(g["name"])}</div>'
                f'<div style="font-size:14px;color:{theme.MUTED}">{theme.esc(g.get("developer") or "")} · '
                f'{theme.esc(g.get("genre") or "")}</div></div>'
                f'<span class="mono" style="font-weight:700">{rating}</span></div>'
                f'<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0 6px;'
                f'background:{theme.PANEL_2};border-radius:10px;padding:12px">'
                f'<div><div class="gr-label">Installs</div><div class="mono" style="font-weight:700">'
                f'{theme.esc(str(g.get("installs") or "?").replace(",000,000", "M").replace(",000", "K"))}</div></div>'
                f'<div><div class="gr-label">Reviews</div><div class="mono" style="font-weight:700">{int(g["n_reviews"])}</div></div>'
                f'<div><div class="gr-label">Labeled</div><div class="mono" style="font-weight:700;color:{theme.ACCENT}">'
                f'{labeled_share:.0%}</div></div></div>'
                f'<div style="font-size:13px;color:{theme.MUTED}">Reviews from '
                f'<span class="mono">{theme.esc(str(g.get("first_review") or "")[:7])}</span> to '
                f'<span class="mono">{theme.esc(str(g.get("last_review") or "")[:7])}</span>{by}</div>')
            is_on = g["app_id"] in chosen
            b1, b2 = st.columns([3, 2])
            if b1.button("✓ Comparing" if is_on else "+ Compare", key=f"cmp_{g['app_id']}",
                         type="primary" if is_on else "secondary", width="stretch"):
                toggle(g["app_id"])
                st.rerun()
            with b2.popover("More", width="stretch"):
                if g.get("store_url"):
                    st.link_button("Open on Google Play", g["store_url"], width="stretch",
                                   icon=":material/open_in_new:")
                if not user:
                    st.caption("Sign in to download more reviews.")
                else:
                    if st.button("Download reviews…", key=f"dl_{g['app_id']}", width="stretch",
                                 icon=":material/download:",
                                 help="Newest, older, a date range or one app version"):
                        # dialogs can't open from inside a popover: open it on the next run
                        st.session_state["_dl_open"] = (g["app_id"], g["name"], int(g["n_reviews"]))
                        st.rerun()

st.page_link("pages/add_game.py", label="Missing a game? Add it to the catalog", icon=":material/add_circle:")
