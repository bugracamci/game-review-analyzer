"""Admin: usage, users, catalog moderation, activity log, inbox and app settings."""
import pandas as pd
import plotly.express as px
import streamlit as st

import config
from core import limits, repo
from ui import theme
from ui import actions
from ui.auth import is_admin
from ui.data import db, featured_ids, games_table, refresh_caches, style_fig

user = st.session_state.get("user")
if not is_admin(user):
    st.error("Admins only.")
    st.stop()

theme.page_header("Admin", "Control room")
s = repo.stats(db())
theme.kpis([(label, f"{s[key]:,}") for label, key in
            [("Users", "users"), ("Games", "games"), ("Reviews", "reviews"), ("Labels", "labels"),
             ("Actions (24h)", "actions_24h"), ("New messages", "new_feedback")]])

tab_inbox, tab_users, tab_catalog, tab_activity, tab_settings = st.tabs(
    [f":material/inbox: Inbox ({s['new_feedback']})", ":material/group: Users", ":material/grid_view: Catalog", ":material/history: Activity", ":material/tune: Settings"])

# =============================================================================
with tab_inbox:
    messages = repo.list_feedback(db())
    if not messages:
        st.caption("No messages yet.")
    for m in messages:
        with st.container(border=True):
            st.markdown(f"**{m['kind']}** · {m['name'] or ''} `{m['email']}` · "
                        f"{m['created_at'][:16].replace('T', ' ')} · *{m['status']}*")
            st.text(m["message"])
            c1, c2, _ = st.columns([1, 1, 4])
            if m["status"] != "done" and c1.button("Mark done", key=f"done_{m['id']}"):
                repo.set_feedback_status(db(), m["id"], "done")
                st.rerun()
            c2.link_button("Reply by email", f"mailto:{m['email']}?subject=Game Review Radar")

# =============================================================================
with tab_users:
    users = repo.list_users(db())
    if users.empty:
        st.caption("No users yet.")
    else:
        st.dataframe(users, hide_index=True, width="stretch")
        target = st.selectbox("User", users["email"])
        row = users[users["email"] == target].iloc[0]
        banned = bool(row["is_banned"])
        if st.button("Unban" if banned else "Ban", disabled=target in config.ADMIN_EMAILS):
            repo.update_user(db(), target, is_banned=int(not banned))
            st.rerun()
        signups = pd.to_datetime(users["created_at"], utc=True).dt.date.value_counts().sort_index()
        fig = px.bar(x=signups.index, y=signups.values, labels={"x": "", "y": "New users"})
        fig.update_traces(marker_color="#2a78d6", hovertemplate="%{x}: %{y}<extra></extra>")
        st.plotly_chart(style_fig(fig, 260), width="stretch", theme=None)

# =============================================================================
with tab_catalog:
    games = games_table(include_hidden=True)
    if games.empty:
        st.caption("Catalog is empty.")
    else:
        show = games[["name", "developer", "app_id", "n_reviews", "n_labeled", "added_by",
                      "last_fetched_at", "is_hidden"]]
        st.dataframe(show, hide_index=True, width="stretch")
        names = dict(zip(games["app_id"], games["name"]))
        app_id = st.selectbox("Game", list(names), format_func=names.get)
        g = games[games["app_id"] == app_id].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Unhide" if g["is_hidden"] else "Hide from catalog"):
            repo.set_game_hidden(db(), app_id, not g["is_hidden"])
            refresh_caches()
            st.rerun()
        if c2.button("Refresh + label (server key)"):
            r = actions.run_collect(user, app_id, "us", "en", 400, is_new=False)
            if r:
                actions.run_labeling(user, [app_id], config.DEFAULT_SCHEME_ID)
        confirm = c3.checkbox("Confirm delete")
        if c4.button("Delete game + data", disabled=not confirm, type="primary"):
            repo.delete_game(db(), app_id)
            refresh_caches()
            st.rerun()

# =============================================================================
with tab_activity:
    log = repo.recent_activity(db(), 300)
    if log.empty:
        st.caption("No activity yet.")
    else:
        errors = log[log["status"] == "error"]
        if not errors.empty:
            st.warning(f"{len(errors)} errors in the last {len(log)} actions")
        st.dataframe(log[["created_at", "email", "action", "app_id", "status", "n_calls",
                          "n_items", "details"]], hide_index=True, width="stretch")

# =============================================================================
with tab_settings:
    st.markdown("**Daily limits per user** (admins have none)")
    current = limits.get_limits(db())
    with st.form("limits"):
        new_games = st.number_input("New games per day", 0, 100, int(current["new_games_per_day"]))
        runs = st.number_input("Labeling / insight / refresh runs per day", 0, 500,
                               int(current["label_runs_per_day"]))
        if st.form_submit_button("Save limits"):
            repo.set_setting(db(), "limits", {"new_games_per_day": int(new_games),
                                              "label_runs_per_day": int(runs)})
            st.toast("Saved")

    st.markdown("**Featured comparison** (what visitors see first)")
    games = games_table()
    names = dict(zip(games["app_id"], games["name"])) if not games.empty else {}
    with st.form("featured"):
        chosen = st.multiselect("Games", list(names), format_func=names.get,
                                default=[a for a in featured_ids() if a in names], max_selections=8)
        if st.form_submit_button("Save featured games"):
            repo.set_setting(db(), "featured_app_ids", chosen)
            st.toast("Saved")

    st.markdown("**About page – owner info**")
    owner = {**config.DEFAULT_OWNER, **(repo.get_setting(db(), "owner", {}) or {})}
    with st.form("owner"):
        values = {k: st.text_input(k.replace("owner_", "").replace("_", " ").title(), value=v)
                  for k, v in owner.items()}
        if st.form_submit_button("Save owner info"):
            repo.set_setting(db(), "owner", values)
            st.toast("Saved")
