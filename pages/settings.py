"""Settings: API keys, AI options, custom topic lists, profile and account."""
import re

import streamlit as st
from html import escape

import config
from core import crypto, repo
from core.llm import BadKey, list_gemini_models
from ui import theme
from ui.auth import require_login
from ui.data import db, refresh_caches, user_prefs



@st.cache_data(ttl=3600, show_spinner=False)
def _models(key: str) -> list[str]:
    return list_gemini_models(key)


user = st.session_state.get("user")
theme.page_header("You", "Settings")
require_login(user, "change settings")
email = user["email"]
prefs = user_prefs(user)

tab_keys, tab_ai, tab_topics, tab_profile, tab_account = st.tabs(
    [":material/key: API keys", ":material/smart_toy: AI options", ":material/label: Topic lists", ":material/person: Profile", ":material/lock: Privacy & account"])

# =============================================================================
with tab_keys:
    st.markdown("Game Review Radar uses **your own** AI key, so it stays free for everyone. "
                "A free Gemini key takes one minute: "
                "[aistudio.google.com/apikey](https://aistudio.google.com/apikey).")
    can_remember = crypto.is_configured()
    for provider, title, link in [("gemini", "Google Gemini", "https://aistudio.google.com/apikey"),
                                  ("groq", "Groq (optional fallback)", "https://console.groq.com/keys")]:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            saved = repo.get_api_key(db(), email, provider)
            session = st.session_state.get(f"{provider}_key")
            if saved:
                st.success(f"Saved on your account (encrypted): `{crypto.mask(saved)}`")
            elif session:
                st.info(f"Used for this session only: `{crypto.mask(session)}` – "
                        "forgotten when you close the tab.")
            with st.form(f"key_{provider}", clear_on_submit=True):
                key = st.text_input("API key", type="password", placeholder="Paste your key")
                remember = st.checkbox("Remember on my account (encrypted)", value=False,
                                       disabled=not can_remember,
                                       help="Stored encrypted; only the server can decrypt it, "
                                            "and only to run your own requests.")
                if st.form_submit_button("Save key") and key.strip():
                    key = key.strip()
                    if provider == "gemini":
                        try:
                            n = len(list_gemini_models(key))
                            st.toast(f"Key works – {n} models available")
                        except BadKey:
                            st.error("Google rejected this key. Check it and try again.")
                            st.stop()
                        except Exception:  # noqa: BLE001 - network hiccup: accept the key
                            pass
                    st.session_state[f"{provider}_key"] = key
                    if remember:
                        repo.save_api_key(db(), email, provider, key)
                    st.rerun()
            if saved or session:
                if st.button("Remove key", key=f"rm_{provider}"):
                    st.session_state.pop(f"{provider}_key", None)
                    repo.save_api_key(db(), email, provider, None)
                    st.rerun()
    if not can_remember:
        st.caption("Saving keys is disabled on this server (no encryption key configured). "
                   "Keys are kept for the current session only.")

# =============================================================================
with tab_ai:
    st.markdown("Defaults work well on a free key. Change them if you have a paid key "
                "or want more data.")
    with st.form("ai_prefs"):
        provider = st.radio("Provider", ["gemini", "groq"], horizontal=True,
                            index=0 if prefs["provider"] == "gemini" else 1,
                            format_func=lambda p: {"gemini": "Google Gemini",
                                                   "groq": "Groq (Llama)"}[p])
        key = st.session_state.get("gemini_key") or repo.get_api_key(db(), email, "gemini")
        models = list(config.GEMINI_FALLBACK_MODELS)
        if key:
            try:
                models = _models(key) or models
            except Exception:  # noqa: BLE001
                pass
        if prefs["model"] not in models:
            models.insert(0, prefs["model"])
        model = st.selectbox("Gemini model", models, index=models.index(prefs["model"]),
                             help="Flash-Lite models have the largest free quota. "
                                  "If a model is busy or out of quota, the app switches "
                                  "to a fallback automatically.")
        batch = st.slider("Reviews per AI request", 10, 100, int(prefs["batch_size"]), step=5,
                          help="Bigger batches = fewer requests, but a slightly higher chance "
                               "the model skips a review (skipped ones are retried).")
        per_game = st.slider("Default reviews per new game", 100, config.MAX_REVIEWS_PER_GAME,
                             int(prefs["reviews_per_game"]), step=100)
        markets = {m[0]: m[2] for m in config.MARKETS}
        market = st.selectbox("Default store country", list(markets),
                              index=list(markets).index(prefs["market"])
                              if prefs["market"] in markets else 0,
                              format_func=markets.get)
        if st.form_submit_button("Save", type="primary"):
            repo.update_user(db(), email, prefs={**prefs, "provider": provider, "model": model,
                                                  "batch_size": batch,
                                                  "reviews_per_game": per_game,
                                                  "market": market})
            st.toast("Saved")
            st.rerun()

# =============================================================================
with tab_topics:
    st.markdown("The standard topic list is the same for everyone, so games stay comparable. "
                "Create your **own topic list** to look at reviews through your own lens "
                "(e.g. *energy system, guild features, PvP*). Your lists are private.")
    for s in repo.list_schemes(db(), email)[1:]:
        with st.container(border=True):
            cols = st.columns([5, 1])
            cols[0].markdown(f"**{escape(s['name'])}**  \n<small>"
                             + escape(", ".join(s["labels"].values()))
                             + "</small>", unsafe_allow_html=True)
            if cols[1].button("Delete", key=f"del_s_{s['id']}"):
                repo.delete_scheme(db(), email, s["id"])
                refresh_caches()
                st.rerun()
    with st.form("new_scheme", clear_on_submit=True):
        name = st.text_input("List name", placeholder="e.g. Economy deep-dive")
        text = st.text_area(
            "One topic per line:  Label: what it covers",
            height=180,
            placeholder="Energy system: stamina, waiting, refills\n"
                        "Gacha fairness: drop rates, pity, duplicates\n"
                        "Guilds & social: clans, chat, co-op")
        if st.form_submit_button("Create topic list") and name.strip() and text.strip():
            topics = {}
            for line in text.strip().splitlines()[:12]:
                label, _, desc = line.partition(":")
                key = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
                if key:
                    topics[key] = f"{label.strip()} ({desc.strip() or label.strip()})"
            if len(topics) < 2:
                st.error("Add at least two topics.")
            else:
                repo.create_scheme(db(), email, name.strip(), topics)
                st.success("Created. Pick it as **Topic list** in the sidebar, then label the "
                           "selected games with it from the Overview page.")
                refresh_caches()

# =============================================================================
with tab_profile:
    st.markdown("Optional. If you choose to appear on the **Community** page, other small "
                "teams can see what you've contributed and reach you.")
    with st.form("profile"):
        display = st.text_input("Display name", value=user.get("display_name")
                                or user.get("name") or "")
        link = st.text_input("Link (LinkedIn, studio site, itch.io…)",
                             value=user.get("profile_link") or "")
        public = st.toggle("Show me on the Community page and next to games I add",
                           value=bool(user.get("show_in_community")))
        if st.form_submit_button("Save profile", type="primary"):
            if link and not re.match(r"^https?://[^\s()<>\[\]]+$", link.strip()):
                st.error("Please enter a plain web address starting with https://")
            else:
                repo.update_user(db(), email, display_name=display.strip() or None,
                                 profile_link=link.strip() or None,
                                 show_in_community=int(public))
                refresh_caches()
                st.toast("Profile saved")
                st.rerun()

# =============================================================================
with tab_account:
    st.markdown("""
**What Game Review Radar stores about you**
- Your Google email and name (to sign you in).
- Your API keys **only if** you tick "Remember" – encrypted, used only to run your own requests.
- Your settings, saved comparisons and topic lists.
- A log of actions (e.g. "added a game") to enforce fair daily limits.

Games and labels you add become part of the **shared catalog** – that's how the community grows.
Reviews are public Google Play reviews; no reviewer names are stored.
""")
    st.divider()
    st.markdown("**Delete my account**")
    st.caption("Deletes your saved keys, settings, comparisons and topic lists. Games you added "
               "stay in the catalog without your name.")
    confirm = st.text_input("Type DELETE to confirm")
    if st.button("Delete my account", disabled=confirm != "DELETE"):
        repo.delete_user(db(), email)
        for k in ("gemini_key", "groq_key", "_synced_user"):
            st.session_state.pop(k, None)
        refresh_caches()
        st.success("Your account was deleted.")
        if not config.DEV_LOGIN_EMAIL:
            st.logout()
