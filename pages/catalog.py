"""Game Catalog: every game the community has analyzed. Pick games to compare."""
from html import escape

import pandas as pd
import streamlit as st

from ui import actions
from ui.data import games_table, select_games, selected_ids, user_prefs

user = st.session_state.get("user")
st.title("Game Catalog")
st.caption("Every game analyzed by the community. Tick games and compare them – "
           "anyone can browse, signed-in users can add and refresh games.")

games = games_table()
if games.empty:
    st.info("No games yet. Add the first one on **Add a Game**.")
    st.stop()

c1, c2 = st.columns([3, 1])
query = c1.text_input("Search", placeholder="Game, developer or genre")
sort = c2.selectbox("Sort by", ["Name", "Most reviews", "Recently updated", "Store rating"])
view = games.copy()
if query.strip():
    q = query.strip().lower()
    view = view[view[["name", "developer", "genre"]].fillna("").apply(
        lambda r: q in " ".join(r).lower(), axis=1)]
view = {"Name": view.sort_values("name"),
        "Most reviews": view.sort_values("n_reviews", ascending=False),
        "Recently updated": view.sort_values("last_fetched_at", ascending=False),
        "Store rating": view.sort_values("avg_rating", ascending=False)}[sort]

chosen = set(selected_ids())
st.markdown(f"**{len(view)} games** · {len(chosen)} selected for comparison")

for start in range(0, len(view), 3):
    for col, (_, g) in zip(st.columns(3), view.iloc[start:start + 3].iterrows()):
        with col.container(border=True):
            top = st.columns([1, 4])
            if g.get("icon_url"):
                top[0].image(g["icon_url"], width=56)
            top[1].markdown(f"**{escape(str(g['name']))}**  \n"
                            f"<small>{escape(str(g.get('developer') or ''))} · "
                            f"{escape(str(g.get('genre') or ''))}</small>",
                            unsafe_allow_html=True)
            labeled_share = g["n_labeled"] / g["n_reviews"] if g["n_reviews"] else 0
            rating = f"{g['avg_rating']:.1f}★" if pd.notna(g.get("avg_rating")) else "–"
            st.caption(f"{rating} · {g.get('installs') or '?'} installs · "
                       f"{int(g['n_reviews'])} reviews ({labeled_share:.0%} labeled)")
            updated = str(g.get("last_fetched_at") or "")[:10]
            by = ""
            if g.get("added_by_public") and g.get("added_by_name"):
                by = f" · added by {g['added_by_name']}"
            st.caption(f"Updated {updated}{by}")
            is_on = g["app_id"] in chosen
            if st.checkbox("Compare", value=is_on, key=f"cmp_{g['app_id']}") != is_on:
                ids = [a for a in selected_ids() if a != g["app_id"]]
                if not is_on:
                    ids.append(g["app_id"])
                select_games(ids)
                st.rerun()
            if user:
                with st.popover("More"):
                    if g.get("store_url"):
                        st.link_button("Open on Google Play", g["store_url"])
                    st.caption("Download the newest reviews and label them with your key.")
                    if st.button("Refresh reviews", key=f"ref_{g['app_id']}"):
                        prefs = user_prefs(user)
                        r = actions.run_collect(user, g["app_id"], "us", "en",
                                                int(prefs["reviews_per_game"]), is_new=False)
                        if r and r["added"]:
                            actions.run_labeling(user, [g["app_id"]], "default")
                        st.rerun()

st.divider()
st.caption("Missing a game? Add it on **Add a Game**, or request it on **About & Community**.")
