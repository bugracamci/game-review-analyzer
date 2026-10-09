"""Shared data access for the Streamlit pages: cached loaders, the current
game selection, colors, chart style and the user's LLM settings."""
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

import config
from core import repo
from core.db import get_db
from core.llm import LLMConfig

from ui.theme import GAME_COLORS, HEATMAP_SCALE, SENTIMENT_COLORS  # noqa: F401 (re-exported)
from ui.theme import style_fig as _style_fig

MAX_COMPARE = len(GAME_COLORS)
SENTIMENT_ORDER = ["negative", "neutral", "positive"]


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


# --- Global filters + shareable links ------------------------------------------
PERIODS = {"all": "All time", "7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days",
           "180": "Last 180 days"}
FILTER_DEFAULTS = {"f_period": "all", "f_stars": (1, 5)}


def active_filters() -> list[str]:
    """Human-readable list of filters that are switched on (empty = showing everything)."""
    out = []
    if st.session_state.get("f_period", "all") != "all":
        out.append(PERIODS[st.session_state["f_period"]])
    lo, hi = st.session_state.get("f_stars", (1, 5))
    if (lo, hi) != (1, 5):
        out.append(f"{lo}★" if lo == hi else f"{lo}–{hi}★")
    return out


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    period = st.session_state.get("f_period", "all")
    if period != "all":
        since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(period))
        df = df[df["review_date"] >= since]
    lo, hi = st.session_state.get("f_stars", (1, 5))
    return df[df["rating"].between(lo, hi)]


def _read_query_params(names: dict) -> None:
    """First run of a session: take games + filters from a shared link (?games=...&period=...)."""
    if st.session_state.get("_qp_read"):
        return
    st.session_state["_qp_read"] = True
    qp = st.query_params
    ids = [a for a in qp.get("games", "").split(",") if a in names]
    if ids:
        st.session_state["selected_games"] = ids[:MAX_COMPARE]
    if qp.get("period") in PERIODS:
        st.session_state["f_period"] = qp["period"]
    try:
        lo, hi = (int(x) for x in qp.get("stars", "").split("-"))
        if 1 <= lo <= hi <= 5:
            st.session_state["f_stars"] = (lo, hi)
    except ValueError:
        pass


def share_params() -> dict:
    params = {"games": ",".join(selected_ids())}
    if st.session_state.get("f_period", "all") != "all":
        params["period"] = st.session_state["f_period"]
    if tuple(st.session_state.get("f_stars", (1, 5))) != (1, 5):
        params["stars"] = "-".join(str(x) for x in st.session_state["f_stars"])
    return params


def share_url() -> str:
    """Link that opens the current page with the same games and filters."""
    base = (st.context.url or config.PUBLIC_URL).split("?")[0]
    return f"{base}?{urlencode(share_params(), safe=',')}"


def _reset_filters() -> None:
    for k, v in FILTER_DEFAULTS.items():
        st.session_state[k] = v


def sidebar_selectors(user: dict | None) -> None:
    games = games_table()
    if games.empty:
        st.sidebar.info("The catalog is empty.")
        return
    names = dict(zip(games["app_id"], games["name"]))
    _read_query_params(names)
    if "_pending_selection" in st.session_state:
        st.session_state["selected_games"] = st.session_state.pop("_pending_selection")
    if "_pending_scheme" in st.session_state:
        st.session_state["scheme_id"] = st.session_state.pop("_pending_scheme")
    if "selected_games" not in st.session_state:
        st.session_state["selected_games"] = [a for a in featured_ids() if a in names] \
            or list(names)[:4]
    # drop games that disappeared from the catalog (hidden/deleted)
    st.session_state["selected_games"] = [a for a in selected_ids() if a in names]
    st.sidebar.multiselect("Comparing", list(names), key="selected_games",
                           format_func=lambda a: names.get(a, a), max_selections=MAX_COMPARE)

    for k, v in FILTER_DEFAULTS.items():
        st.session_state.setdefault(k, v)
    on = active_filters()
    with st.sidebar.expander(f"Filters · {len(on)} on" if on else "Filters",
                             icon=":material/filter_list:", expanded=bool(on)):
        st.selectbox("Review date", list(PERIODS), key="f_period", format_func=PERIODS.get)
        st.slider("Stars", 1, 5, key="f_stars")
        if on:
            st.button("Reset filters", on_click=_reset_filters, width="stretch")
    with st.sidebar.popover("Share this view", icon=":material/link:", width="stretch"):
        st.caption("Anyone with this link sees the same games and filters on this page.")
        st.code(share_url(), language=None, wrap_lines=True)
    # keep the address bar in sync, so copying the browser URL also works
    for k, v in share_params().items():
        if st.query_params.get(k) != v:
            st.query_params[k] = v
    for k in ("period", "stars"):
        if k in st.query_params and k not in share_params():
            del st.query_params[k]
    schemes = repo.list_schemes(db(), user["email"] if user else None)
    if len(schemes) > 1:
        scheme_names = {s["id"]: s["name"] for s in schemes}
        st.session_state.setdefault("scheme_id", config.DEFAULT_SCHEME_ID)
        if st.session_state["scheme_id"] not in scheme_names:
            st.session_state["scheme_id"] = config.DEFAULT_SCHEME_ID
        st.sidebar.selectbox("Topic list", list(scheme_names), key="scheme_id",
                             format_func=lambda s: scheme_names[s])


def selected_reviews(user: dict | None, filtered: bool = True) -> tuple[pd.DataFrame, dict]:
    scheme = selected_scheme(user)
    df = labeled(tuple(sorted(selected_ids())), scheme["id"])
    return (apply_filters(df) if filtered else df), scheme


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
    return _style_fig(fig, height)


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
