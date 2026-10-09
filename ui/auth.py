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
    from ui.theme import esc, html
    if user:
        label = user.get("display_name") or user.get("name") or user["email"]
        html(f'<div style="display:flex;align-items:center;gap:10px;padding:4px 2px 8px">'
             f'<span style="width:34px;height:34px;border-radius:999px;background:#16223A;color:#7CE3A0;'
             f'display:inline-flex;align-items:center;justify-content:center;font-weight:700">'
             f'{esc(label[:1].upper())}</span><div><div style="font-weight:600">{esc(label)}</div>'
             f'<div style="font-size:12px;color:#8A95A8">{"Admin" if is_admin(user) else "Member"}</div></div></div>',
             st.sidebar)
        if config.DEV_LOGIN_EMAIL:
            st.sidebar.caption("Local dev login")
        elif st.sidebar.button("Sign out", width="stretch"):
            st.logout()
    elif auth_configured():
        html('<div style="font-size:14px;color:#C9D2E0;line-height:1.45;padding:2px 2px 10px">'
             'Free for indie teams. Sign in to add games, export data and save comparisons.</div>',
             st.sidebar)
        if st.sidebar.button("Sign in with Google", type="primary", width="stretch"):
            st.login("google")


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
