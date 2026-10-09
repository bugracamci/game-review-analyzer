"""Shared data access for the Streamlit pages: cached loaders, the current
game selection, colors, chart style and the user's LLM settings."""
import datetime as dt
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

import config
from core import repo
from core.db import get_db
from core.fetcher import version_key
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


# --- Filters, per-game slices and shareable links --------------------------------
# Global filters apply to every game; each game can instead use its own slice (a date
# range, chosen app versions or its latest version) - any combination is allowed.
PERIODS = {"365": "Last 12 months", "180": "Last 6 months", "90": "Last 90 days",
           "30": "Last 30 days", "7": "Last 7 days", "all": "All time", "custom": "Custom range"}
SCOPES = {"global": "Same as above", "range": "Own date range", "versions": "Chosen app versions",
          "latest": "Latest version"}


def _defaults() -> dict:
    today = dt.date.today()
    return {"f_period": config.DEFAULT_PERIOD, "f_stars": (1, 5),
            "f_range": (today - dt.timedelta(days=365), today)}


def _period_bounds() -> tuple | None:
    """(start, end) dates of the global period, or None for all time."""
    period = st.session_state.get("f_period", config.DEFAULT_PERIOD)
    if period == "all":
        return None
    if period == "custom":
        rng = st.session_state.get("f_range")
        return tuple(rng) if rng and len(rng) == 2 else None
    today = dt.date.today()
    return today - dt.timedelta(days=int(period)), today


def _scope(app_id: str) -> str:
    return st.session_state.get(f"scope_{app_id}", "global")


def _fmt_range(a, b) -> str:
    return f"{a:%b %Y}" if (a.year, a.month) == (b.year, b.month) else f"{a:%b %Y}–{b:%b %Y}"


def active_filters() -> list[str]:
    """Human-readable description of the global filters (shown in page headers)."""
    period = st.session_state.get("f_period", config.DEFAULT_PERIOD)
    out = []
    if period == "custom" and _period_bounds():
        out.append(_fmt_range(*_period_bounds()))
    elif period != "custom":
        out.append(PERIODS[period])
    lo, hi = st.session_state.get("f_stars", (1, 5))
    if (lo, hi) != (1, 5):
        out.append(f"{lo}★" if lo == hi else f"{lo}–{hi}★")
    return out


def _between(df: pd.DataFrame, start, end) -> pd.DataFrame:
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    return df[(df["review_date"] >= lo) & (df["review_date"] < hi)]


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the global filters and each game's own slice. A game with its own slice gets
    a label like 'Archero 2 · Jan 2023–Dec 2024' so every chart shows what is compared."""
    if df.empty:
        return df
    parts = []
    for app_id, g in df.groupby("app_id", sort=False):
        name, scope = g["game"].iloc[0], _scope(app_id)
        if scope == "range" and st.session_state.get(f"srange_{app_id}") \
                and len(st.session_state[f"srange_{app_id}"]) == 2:
            a, b = st.session_state[f"srange_{app_id}"]
            g = _between(g, a, b).assign(game=f"{name} · {_fmt_range(a, b)}")
        elif scope == "versions" and st.session_state.get(f"sver_{app_id}"):
            vs = list(st.session_state[f"sver_{app_id}"])
            tag = ", ".join(f"v{v}" for v in vs[:2]) + (f" +{len(vs) - 2}" if len(vs) > 2 else "")
            g = g[g["version"].isin(vs)].assign(game=f"{name} · {tag}")
        elif scope == "latest" and g["version"].notna().any():
            v = max(g["version"].dropna().unique(), key=version_key)
            g = g[g["version"] == v].assign(game=f"{name} · latest (v{v})")
        else:
            bounds = _period_bounds()
            if bounds:
                g = _between(g, *bounds)
        parts.append(g)
    out = pd.concat(parts) if parts else df.iloc[0:0]
    lo, hi = st.session_state.get("f_stars", (1, 5))
    return out[out["rating"].between(lo, hi)]


def _read_query_params(names: dict) -> None:
    """First run of a session: take games, filters and slices from a shared link."""
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
        if qp.get("from") and qp.get("to"):
            st.session_state["f_range"] = (dt.date.fromisoformat(qp["from"]),
                                           dt.date.fromisoformat(qp["to"]))
        lo, hi = (int(x) for x in qp.get("stars", "1-5").split("-"))
        if 1 <= lo <= hi <= 5:
            st.session_state["f_stars"] = (lo, hi)
        for item in qp.get("slices", "").split(";"):
            bits = item.split("~")
            if len(bits) < 2 or bits[0] not in names:
                continue
            app_id, kind = bits[0], bits[1]
            if kind == "r" and len(bits) == 4:
                st.session_state[f"scope_{app_id}"] = "range"
                st.session_state[f"srange_{app_id}"] = (dt.date.fromisoformat(bits[2]),
                                                        dt.date.fromisoformat(bits[3]))
            elif kind == "v" and len(bits) == 3:
                st.session_state[f"scope_{app_id}"] = "versions"
                st.session_state[f"sver_{app_id}"] = bits[2].split("|")
            elif kind == "latest":
                st.session_state[f"scope_{app_id}"] = "latest"
    except ValueError:
        pass  # a hand-edited link with bad values: ignore the rest


def share_params() -> dict:
    params = {"games": ",".join(selected_ids())}
    period = st.session_state.get("f_period", config.DEFAULT_PERIOD)
    if period != config.DEFAULT_PERIOD:
        params["period"] = period
    if period == "custom" and _period_bounds():
        params["from"], params["to"] = (d.isoformat() for d in _period_bounds())
    if tuple(st.session_state.get("f_stars", (1, 5))) != (1, 5):
        params["stars"] = "-".join(str(x) for x in st.session_state["f_stars"])
    slices = []
    for app_id in selected_ids():
        scope = _scope(app_id)
        rng, vs = st.session_state.get(f"srange_{app_id}"), st.session_state.get(f"sver_{app_id}")
        if scope == "range" and rng and len(rng) == 2:
            slices.append(f"{app_id}~r~{rng[0].isoformat()}~{rng[1].isoformat()}")
        elif scope == "versions" and vs:
            slices.append(f"{app_id}~v~{'|'.join(vs)}")
        elif scope == "latest":
            slices.append(f"{app_id}~latest")
    if slices:
        params["slices"] = ";".join(slices)
    return params


def share_url() -> str:
    """Link that opens the current page with the same games, filters and slices."""
    # On Streamlit Cloud the app runs inside a frame at /~/+/; links should use the normal address.
    base = (st.context.url or config.PUBLIC_URL).split("?")[0].replace("/~/+", "")
    return f"{base}?{urlencode(share_params(), safe=',~;|')}"


def _reset_filters() -> None:
    for k, v in _defaults().items():
        st.session_state[k] = v
    for k in [k for k in st.session_state if str(k).startswith(("scope_", "srange_", "sver_"))]:
        del st.session_state[k]


def _filters_ui(names: dict, user: dict | None) -> None:
    for k, v in _defaults().items():
        st.session_state.setdefault(k, v)
    custom = [a for a in selected_ids() if _scope(a) != "global"]
    label = " · ".join(active_filters()) + (f" · {len(custom)} own" if custom else "")
    # a fixed label keeps the expander open while filters change (a new label = a new widget)
    with st.sidebar.expander("Filters", icon=":material/filter_list:"):
        st.selectbox("Review date", list(PERIODS), key="f_period", format_func=PERIODS.get)
        if st.session_state["f_period"] == "custom":
            st.date_input("From – to", key="f_range", format="YYYY-MM-DD",
                          max_value=dt.date.today())
        st.slider("Stars", 1, 5, key="f_stars")
        if selected_ids():
            st.markdown("**Each game**")
            st.caption("Give any game its own date range or app versions – "
                       "e.g. one game's 2023 reviews next to another's latest version.")
            versions = _versions_by_game(user)
            for app_id in selected_ids():
                st.selectbox(names.get(app_id, app_id), list(SCOPES), key=f"scope_{app_id}",
                             format_func=SCOPES.get)
                scope = _scope(app_id)
                if scope == "range":
                    today = dt.date.today()
                    st.session_state.setdefault(f"srange_{app_id}",
                                                (today - dt.timedelta(days=365), today))
                    st.date_input("Dates", key=f"srange_{app_id}", format="YYYY-MM-DD",
                                  max_value=today, label_visibility="collapsed")
                elif scope == "versions":
                    opts = versions.get(app_id, [])
                    st.session_state[f"sver_{app_id}"] = [
                        v for v in st.session_state.get(f"sver_{app_id}", []) if v in opts]
                    st.multiselect("Versions", opts, key=f"sver_{app_id}",
                                   placeholder="Pick versions", label_visibility="collapsed")
        st.button("Reset filters", on_click=_reset_filters, width="stretch")
    st.sidebar.caption(f"Showing: {label}")


def _versions_by_game(user: dict | None) -> dict:
    """Stored app versions per selected game, newest first (with review counts in labels)."""
    df = labeled(tuple(sorted(selected_ids())), selected_scheme(user)["id"])
    if df.empty:
        return {}
    return {a: sorted(g["version"].dropna().unique(), key=version_key, reverse=True)
            for a, g in df.groupby("app_id")}


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
    schemes = repo.list_schemes(db(), user["email"] if user else None)
    if len(schemes) > 1:
        scheme_names = {s["id"]: s["name"] for s in schemes}
        st.session_state.setdefault("scheme_id", config.DEFAULT_SCHEME_ID)
        if st.session_state["scheme_id"] not in scheme_names:
            st.session_state["scheme_id"] = config.DEFAULT_SCHEME_ID
        st.sidebar.selectbox("Topic list", list(scheme_names), key="scheme_id",
                             format_func=lambda s: scheme_names[s])

    _filters_ui(names, user)
    with st.sidebar.popover("Share this view", icon=":material/link:", width="stretch"):
        st.caption("Anyone with this link sees the same games, filters and slices on this page.")
        st.code(share_url(), language=None, wrap_lines=True)
    # keep the address bar in sync, so copying the browser URL also works
    params = share_params()
    for k, v in params.items():
        if st.query_params.get(k) != v:
            st.query_params[k] = v
    for k in ("period", "from", "to", "stars", "slices"):
        if k in st.query_params and k not in params:
            del st.query_params[k]


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
