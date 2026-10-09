"""Small building blocks reused by several pages."""
import streamlit as st

from core import repo
from ui import actions
from ui.data import db, games_table, selected_ids, selected_reviews


def analysis_data(title: str, caption: str):
    """Common top of every analysis page: title, data for the selection, label notice.

    Returns (user, df, scheme) or stops the page if there is nothing to show.
    """
    user = st.session_state.get("user")
    st.title(title)
    st.caption(caption)
    ids = selected_ids()
    if not ids:
        st.info("Pick games to compare in the sidebar, or browse the **Game Catalog**.")
        st.stop()
    df, scheme = selected_reviews(user)
    unlabeled_notice(user, ids, scheme)
    if df.empty:
        st.stop()
    return user, df, scheme


def unlabeled_notice(user: dict | None, app_ids: list[str], scheme: dict) -> None:
    """Tell the user if some reviews aren't labeled yet (for this topic list) and offer to fix it."""
    missing = len(repo.unlabeled_reviews(db(), app_ids, scheme["id"]))
    if not missing:
        return
    custom = scheme["id"] != "default"
    text = (f"**{missing} reviews** of the selected games are not labeled"
            + (f" with your topic list *{scheme['name']}*" if custom else "") + " yet.")
    with st.container(border=True):
        st.markdown(text)
        if not user:
            st.caption("Sign in and add your free Gemini key to label them – "
                       "your work becomes available to everyone in the catalog.")
            return
        calls = -(-missing // 25)
        st.caption(f"About {calls} AI requests with your own API key. Progress is saved after "
                   "every batch, so you can stop and continue later.")
        if st.button(f"Label {missing} reviews now", type="primary"):
            actions.run_labeling(user, app_ids, scheme["id"])
            st.rerun()


def game_names() -> dict:
    games = games_table(include_hidden=True)
    return dict(zip(games["app_id"], games["name"])) if not games.empty else {}


def export_buttons(user: dict | None, df, labels: dict, name: str) -> None:
    """CSV / Excel / JSON download buttons for a set of labeled reviews (sign-in required)."""
    from core import exports
    if not user:
        st.caption("Sign in (free) to download this data as CSV, Excel or JSON.")
        return
    st.caption(f"{len(df):,} labeled reviews · {df['game'].nunique()} games")
    c1, c2, c3 = st.columns(3)
    stamp = __import__("datetime").date.today().isoformat()
    log = lambda fmt: repo.log_activity(db(), user["email"], "export", details={"format": fmt})  # noqa: E731
    c1.download_button("⬇️ CSV", exports.to_csv(df, labels), f"{name}-{stamp}.csv",
                       "text/csv", width="stretch", on_click=log, args=("csv",))
    c2.download_button("⬇️ Excel", exports.to_excel(df, labels), f"{name}-{stamp}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch", on_click=log, args=("xlsx",))
    c3.download_button("⬇️ JSON", exports.to_json(df, labels), f"{name}-{stamp}.json",
                       "application/json", width="stretch", on_click=log, args=("json",))
