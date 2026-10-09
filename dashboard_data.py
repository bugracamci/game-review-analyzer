"""Shared data loading and chart styling for the Streamlit pages.

The dashboard only READS data/reviews.db - it never calls an LLM API, so the
live demo is free and fast.
"""
import json
import sqlite3

import pandas as pd
import streamlit as st

from config import DB_PATH, TOPIC_LABELS

# Colors: fixed per entity (a game keeps its color when others are filtered out).
GAME_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SENTIMENT_COLORS = {"negative": "#e34948", "neutral": "#c9c8c3", "positive": "#2a78d6"}
SENTIMENT_ORDER = ["negative", "neutral", "positive"]
HEATMAP_SCALE = ["#f3f8fe", "#9ec5f4", "#3987e5", "#184f95"]


@st.cache_data
def load_reviews() -> pd.DataFrame:
    """One row per review, joined with its labels and game name."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """SELECT r.review_id, g.name AS game, r.rating, r.content, r.version,
                      r.thumbs_up, r.review_date, c.sentiment, c.topics, c.feature_request
               FROM reviews r
               JOIN games g ON g.app_id = r.app_id
               JOIN classifications c ON c.review_id = r.review_id""",
            conn,
        )
    df["review_date"] = pd.to_datetime(df["review_date"], errors="coerce", utc=True)
    df["topics"] = df["topics"].apply(lambda t: json.loads(t) if t else ["other"])
    return df


@st.cache_data
def load_games() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM games ORDER BY name", conn)


@st.cache_data
def load_latest_insights() -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT created_at, model, content FROM insights ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {"created_at": row[0], "model": row[1], **json.loads(row[2])}


def explode_topics(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (review, topic) - a review with 2 topics appears twice."""
    out = df.explode("topics").rename(columns={"topics": "topic"})
    out["topic_label"] = out["topic"].map(TOPIC_LABELS).fillna(out["topic"])
    return out


def game_color_map(all_games: list[str]) -> dict:
    return {g: GAME_COLORS[i % len(GAME_COLORS)] for i, g in enumerate(sorted(all_games))}


def sidebar_game_filter(df: pd.DataFrame) -> None:
    """Sidebar multiselect, rendered once in app.py so the choice survives page switches."""
    games = sorted(df["game"].unique())
    st.sidebar.multiselect("Games to compare", games, default=games, key="selected_games")
    st.sidebar.caption(f"{len(df):,} labeled Google Play reviews (US store)")


def filtered_reviews() -> pd.DataFrame:
    df = load_reviews()
    chosen = st.session_state.get("selected_games") or sorted(df["game"].unique())
    return df[df["game"].isin(chosen)]


def style_fig(fig, height: int = 380):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        font=dict(size=13),
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.07)")
    return fig
