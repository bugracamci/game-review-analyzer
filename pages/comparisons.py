"""My Comparisons & Export: save game sets, reload them, download their data."""
import streamlit as st

from core import repo
from ui.auth import require_login
from ui.components import export_buttons, game_names
from ui.data import db, labeled, select_games, selected_ids, selected_scheme

user = st.session_state.get("user")
st.title("My comparisons & export")
st.caption("Save the games you're comparing, come back to them later and download the data.")
require_login(user, "save comparisons and download data")

names = game_names()
scheme = selected_scheme(user)

# --- Save the current selection ---------------------------------------------------
st.subheader("Save the current selection")
current = selected_ids()
if not current:
    st.info("Pick games in the sidebar first.")
else:
    st.markdown(" · ".join(names.get(a, a) for a in current)
                + (f"  \n<small>Topic list: {scheme['name']}</small>"), unsafe_allow_html=True)
    with st.form("save_cmp", clear_on_submit=True):
        name = st.text_input("Name", placeholder="e.g. Survivor-like competitors, Q4")
        if st.form_submit_button("Save comparison", type="primary") and name.strip():
            repo.save_comparison(db(), user["email"], name.strip(), current, scheme["id"])
            st.success("Saved.")

# --- Saved comparisons --------------------------------------------------------------
st.subheader("Saved comparisons")
saved = repo.list_comparisons(db(), user["email"])
if not saved:
    st.caption("Nothing saved yet.")
for c in saved:
    with st.container(border=True):
        cols = st.columns([5, 1, 1])
        cols[0].markdown(f"**{c['name']}**  \n<small>"
                         + " · ".join(names.get(a, a + ' (removed)') for a in c["app_ids"])
                         + f" · saved {c['created_at'][:10]}</small>", unsafe_allow_html=True)
        if cols[1].button("Open", key=f"open_{c['id']}"):
            select_games([a for a in c["app_ids"] if a in names], c["scheme_id"])
            st.switch_page("pages/overview.py")
        if cols[2].button("Delete", key=f"del_{c['id']}"):
            repo.delete_comparison(db(), user["email"], c["id"])
            st.rerun()

# --- Export -----------------------------------------------------------------------
st.subheader("Download data")
st.caption("Every labeled review of the games in the sidebar: date, stars, sentiment, topics, "
           "feature request and the review text. Excel adds a summary and a feature-request sheet.")
if current:
    df = labeled(tuple(sorted(current)), scheme["id"])
    if df.empty:
        st.info("These games have no labeled reviews yet.")
    else:
        export_buttons(user, df, scheme["labels"], "game-review-radar")
