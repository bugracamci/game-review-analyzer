"""All games: every game the community has analyzed. Pick games to compare."""
import pandas as pd
import streamlit as st

from ui import actions, theme
from ui.data import games_table, select_games, selected_ids, user_prefs

user = st.session_state.get("user")
games = games_table()
theme.page_header(f"{len(games)} games · {int(games['n_labeled'].sum()) if not games.empty else 0:,} "
                  "labeled reviews", "Game catalog",
                  "Every game analyzed by the community. Pick games to compare them.")
if games.empty:
    st.info("No games yet. Add the first one on **Add a game**.")
    st.stop()

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
                f'<div style="font-size:13px;color:{theme.MUTED}">Updated {theme.esc(str(g.get("last_fetched_at") or "")[:10])}{by}</div>')
            is_on = g["app_id"] in chosen
            b1, b2 = st.columns([3, 2])
            if b1.button("✓ Comparing" if is_on else "+ Compare", key=f"cmp_{g['app_id']}",
                         type="primary" if is_on else "secondary", width="stretch"):
                toggle(g["app_id"])
                st.rerun()
            with b2.popover("More", width="stretch"):
                if g.get("store_url"):
                    st.link_button("Open on Google Play", g["store_url"])
                if user:
                    st.caption("Download the newest reviews and label them with your key.")
                    if st.button("Refresh reviews", key=f"ref_{g['app_id']}"):
                        prefs = user_prefs(user)
                        r = actions.run_collect(user, g["app_id"], "us", "en",
                                                int(prefs["reviews_per_game"]), is_new=False)
                        if r and r["added"]:
                            actions.run_labeling(user, [g["app_id"]], "default")
                        st.rerun()

st.page_link("pages/add_game.py", label="Missing a game? Add it to the catalog", icon=":material/add_circle:")
