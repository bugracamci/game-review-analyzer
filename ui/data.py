"""Shared data access for the Streamlit pages: cached loaders, the current
game selection, colors, chart style and the user's LLM settings."""
import pandas as pd
import streamlit as st

import config
from core import repo
from core.db import get_db
from core.llm import LLMConfig

GAME_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
               "#e34948"]
MAX_COMPARE = len(GAME_COLORS)
SENTIMENT_COLORS = {"negative": "#e34948", "neutral": "#c9c8c3", "positive": "#2a78d6"}
SENTIMENT_ORDER = ["negative", "neutral", "positive"]
HEATMAP_SCALE = ["#f3f8fe", "#9ec5f4", "#3987e5", "#184f95"]


@st.cache_resource
def db():
    return get_db()


@st.cache_data(ttl=300, show_spinner=False)
def games_table(include_hidden: bool = False, scheme_id: str = config.DEFAULT_SCHEME_ID):
    return repo.list_games(db(), include_hidden=include_hidden, scheme_id=scheme_id)


@st.cache_data(ttl=300, show_spinner="Loading reviews…")
def labeled(app_ids: tuple, scheme_id: str) -> pd.DataFrame:
    return repo.load_labeled(db(), list(app_ids), scheme_id)


def refresh_caches() -> None:
    """Call after any write so every page shows fresh data."""
    st.cache_data.clear()


# --- Selection (set in the sidebar, used by every analysis page) ---------------
def featured_ids() -> list[str]:
    return repo.get_setting(db(), "featured_app_ids", config.FEATURED_APP_IDS)


def selected_ids() -> list[str]:
    return list(st.session_state.get("selected_games") or [])


def selected_scheme(user: dict | None) -> dict:
    scheme_id = st.session_state.get("scheme_id", config.DEFAULT_SCHEME_ID)
    scheme = repo.get_scheme(db(), scheme_id)
    owner = scheme.get("owner_email")
    if owner and (not user or owner != user["email"]):
        return repo.default_scheme()
    return scheme


def select_games(app_ids: list[str], scheme_id: str | None = None) -> None:
    """Change the sidebar selection from a page. Call st.rerun() right after."""
    st.session_state["_pending_selection"] = list(app_ids)[:MAX_COMPARE]
    if scheme_id:
        st.session_state["_pending_scheme"] = scheme_id


def sidebar_selectors(user: dict | None) -> None:
    games = games_table()
    if games.empty:
        st.sidebar.info("The catalog is empty.")
        return
    names = dict(zip(games["app_id"], games["name"]))
    if "_pending_selection" in st.session_state:
        st.session_state["selected_games"] = st.session_state.pop("_pending_selection")
    if "_pending_scheme" in st.session_state:
        st.session_state["scheme_id"] = st.session_state.pop("_pending_scheme")
    if "selected_games" not in st.session_state:
        st.session_state["selected_games"] = [a for a in featured_ids() if a in names] \
            or list(names)[:4]
    # drop games that disappeared from the catalog (hidden/deleted)
    st.session_state["selected_games"] = [a for a in selected_ids() if a in names]
    st.sidebar.multiselect("Games to compare", list(names), key="selected_games",
                           format_func=lambda a: names.get(a, a), max_selections=MAX_COMPARE)
    schemes = repo.list_schemes(db(), user["email"] if user else None)
    if len(schemes) > 1:
        scheme_names = {s["id"]: s["name"] for s in schemes}
        st.session_state.setdefault("scheme_id", config.DEFAULT_SCHEME_ID)
        if st.session_state["scheme_id"] not in scheme_names:
            st.session_state["scheme_id"] = config.DEFAULT_SCHEME_ID
        st.sidebar.selectbox("Topic list", list(scheme_names), key="scheme_id",
                             format_func=lambda s: scheme_names[s])


def selected_reviews(user: dict | None) -> tuple[pd.DataFrame, dict]:
    scheme = selected_scheme(user)
    return labeled(tuple(sorted(selected_ids())), scheme["id"]), scheme


def color_map(app_names: list[str]) -> dict:
    """Keep each game's color stable while the selection changes."""
    current = st.session_state.setdefault("_colors", {})
    for name in list(current):
        if name not in app_names:
            del current[name]
    free = [c for c in GAME_COLORS if c not in current.values()]
    for name in app_names:
        if name not in current and free:
            current[name] = free.pop(0)
    return current


def style_fig(fig, height: int = 380):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36, b=8),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      font=dict(size=13), bargap=0.25)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.07)")
    return fig


def explode_topics(df: pd.DataFrame, labels: dict) -> pd.DataFrame:
    out = df.explode("topics").rename(columns={"topics": "topic"})
    out["topic_label"] = out["topic"].map(labels).fillna(out["topic"])
    return out


# --- The user's AI settings ------------------------------------------------------
def user_prefs(user: dict | None) -> dict:
    defaults = {"provider": config.DEFAULT_PROVIDER, "model": config.DEFAULT_GEMINI_MODEL,
                "batch_size": config.DEFAULT_BATCH_SIZE,
                "reviews_per_game": config.DEFAULT_REVIEWS_PER_GAME, "market": "us"}
    return {**defaults, **((user or {}).get("prefs") or {})}


def user_api_key(user: dict, provider: str) -> str | None:
    """Session key first, then the saved (encrypted) key, then - for admins - the server key."""
    key = st.session_state.get(f"{provider}_key")
    if key:
        return key
    key = repo.get_api_key(db(), user["email"], provider)
    if key:
        return key
    if user.get("is_admin"):
        return config.GEMINI_API_KEY if provider == "gemini" else config.GROQ_API_KEY
    return None


def user_llm(user: dict, log=None) -> LLMConfig | None:
    prefs = user_prefs(user)
    provider = prefs["provider"]
    key = user_api_key(user, provider)
    if not key:
        return None
    if provider == "groq":
        return LLMConfig(api_key=key, provider="groq", model=prefs.get("groq_model")
                         or config.DEFAULT_GROQ_MODEL, fallbacks=[], log=log or print)
    fallbacks = [m for m in config.GEMINI_FALLBACK_MODELS if m != prefs["model"]]
    return LLMConfig(api_key=key, model=prefs["model"], fallbacks=fallbacks, log=log or print)
