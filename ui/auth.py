"""Who is using the app? Google sign-in via Streamlit's built-in st.login.

- Visitors can browse every analysis without signing in.
- Signing in (free) is needed to add games, label, export and save comparisons.
- Admins are the emails listed in ADMIN_EMAILS.
- DEV_LOGIN_EMAIL fakes a signed-in user for local testing only.
"""
import streamlit as st

import config
from core import repo
from ui.data import db


def auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:  # noqa: BLE001 - no secrets file at all
        return False


def _user_logged_in() -> bool:
    try:
        return bool(st.user.is_logged_in)
    except Exception:  # noqa: BLE001
        return False


def current_user() -> dict | None:
    """The signed-in user's database record (plus is_admin), or None."""
    if config.DEV_LOGIN_EMAIL:
        email, name = config.DEV_LOGIN_EMAIL, "Dev User"
    elif auth_configured() and _user_logged_in():
        email, name = str(st.user.email).lower(), st.user.get("name")
    else:
        return None

    if st.session_state.get("_synced_user") != email:  # once per session
        repo.upsert_user(db(), email, name)
        st.session_state["_synced_user"] = email
    user = repo.get_user(db(), email) or {"email": email, "name": name, "prefs": {}}
    user["is_admin"] = email in config.ADMIN_EMAILS
    return user


def is_admin(user: dict | None) -> bool:
    return bool(user and user.get("is_admin"))


def sidebar_account(user: dict | None) -> None:
    if user:
        label = user.get("display_name") or user.get("name") or user["email"]
        st.sidebar.markdown(f"**👤 {label}**" + (" · admin" if is_admin(user) else ""))
        if config.DEV_LOGIN_EMAIL:
            st.sidebar.caption("Local dev login")
        elif st.sidebar.button("Sign out", width="stretch"):
            st.logout()
    elif auth_configured():
        if st.sidebar.button("Sign in with Google", type="primary", width="stretch"):
            st.login("google")
        st.sidebar.caption("Free. Lets you add games, export data and save comparisons.")


def require_login(user: dict | None, what: str = "use this page") -> None:
    """Stop the page with a friendly sign-in prompt if nobody is signed in."""
    if user:
        if user.get("is_banned"):
            st.error("This account has been suspended. Contact the admin on the Community page.")
            st.stop()
        return
    st.info(f"Sign in (free, with Google) to {what}.")
    if auth_configured() and st.button("Sign in with Google", type="primary"):
        st.login("google")
    st.stop()
