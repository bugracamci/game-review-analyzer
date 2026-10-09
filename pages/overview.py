"""Overview: how players feel about each game and what they talk about."""
import pandas as pd
import plotly.express as px
import streamlit as st

from config import TOPIC_LABELS
from dashboard_data import (HEATMAP_SCALE, SENTIMENT_COLORS, SENTIMENT_ORDER,
                            explode_topics, filtered_reviews, load_games, style_fig)

st.title("What do players love and hate?")
st.caption("Survivor-like / arena mobile games compared through their latest Google Play reviews.")

df = filtered_reviews()
if df.empty:
    st.info("Select at least one game in the sidebar.")
    st.stop()

games_info = load_games().set_index("name")

# --- KPI cards per game ------------------------------------------------------
st.subheader("At a glance")
cols = st.columns(len(df["game"].unique()))
for col, (game, g) in zip(cols, df.groupby("game")):
    neg = (g["sentiment"] == "negative").mean()
    pos = (g["sentiment"] == "positive").mean()
    store = games_info.loc[game, "avg_rating"] if game in games_info.index else None
    with col.container(border=True):
        st.markdown(f"**{game}**")
        st.metric("Positive reviews", f"{pos:.0%}")
        st.metric("Negative reviews", f"{neg:.0%}")
        st.caption(f"{len(g)} reviews · sample avg {g['rating'].mean():.1f}★"
                   + (f" · store {store:.1f}★" if pd.notna(store) else ""))

# --- Sentiment by game -------------------------------------------------------
st.subheader("Sentiment by game")
sent = (df.groupby("game")["sentiment"].value_counts(normalize=True)
          .rename("share").reset_index())
fig = px.bar(sent, y="game", x="share", color="sentiment", orientation="h",
             category_orders={"sentiment": SENTIMENT_ORDER},
             color_discrete_map=SENTIMENT_COLORS, text_auto=".0%",
             labels={"share": "Share of reviews", "game": ""})
fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2,
                  hovertemplate="%{y}<br>%{fullData.name}: %{x:.0%}<extra></extra>")
fig.update_xaxes(tickformat=".0%", range=[0, 1])
st.plotly_chart(style_fig(fig, 80 + 60 * sent["game"].nunique()), use_container_width=True)
st.caption("Sentiment is judged from the review text, not the star rating.")

# --- Topic heatmap -----------------------------------------------------------
st.subheader("What players talk about")
view = st.radio("Reviews", ["All reviews", "Negative reviews only", "Positive reviews only"],
                horizontal=True, label_visibility="collapsed")
subset = {"All reviews": df,
          "Negative reviews only": df[df["sentiment"] == "negative"],
          "Positive reviews only": df[df["sentiment"] == "positive"]}[view]
topics = explode_topics(subset)
counts = subset.groupby("game").size()
share = (topics.groupby(["topic_label", "game"]).size().unstack(fill_value=0)
               .div(counts, axis=1).reindex([TOPIC_LABELS[t] for t in TOPIC_LABELS]).fillna(0))
fig = px.imshow(share, text_auto=".0%", aspect="auto", color_continuous_scale=HEATMAP_SCALE,
                zmin=0, labels={"x": "", "y": "", "color": "Share"})
fig.update_traces(hovertemplate="%{x}<br>%{y}: %{z:.0%} of reviews<extra></extra>")
fig.update_coloraxes(showscale=False)
st.plotly_chart(style_fig(fig, 420), use_container_width=True)
st.caption("Share of reviews mentioning each topic (a review can mention up to 3 topics, "
           "so columns can add up to more than 100%).")

# --- Stars vs sentiment ------------------------------------------------------
st.subheader("Stars vs. what the text says")
left, right = st.columns([2, 1])
with left:
    star = (df.groupby("rating")["sentiment"].value_counts(normalize=True)
              .rename("share").reset_index())
    fig = px.bar(star, x="rating", y="share", color="sentiment",
                 category_orders={"sentiment": SENTIMENT_ORDER},
                 color_discrete_map=SENTIMENT_COLORS,
                 labels={"rating": "Star rating", "share": "Share of reviews"})
    fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2,
                      hovertemplate="%{x}★ · %{fullData.name}: %{y:.0%}<extra></extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(tickvals=[1, 2, 3, 4, 5], ticksuffix="★")
    st.plotly_chart(style_fig(fig, 360), use_container_width=True)
with right:
    high = df[df["rating"] >= 4]
    hidden = high[high["sentiment"] == "negative"]
    st.metric("Hidden complaints", f"{len(hidden) / max(len(high), 1):.0%}",
              help="4-5★ reviews whose text is negative.")
    st.caption("4–5★ reviews whose text is actually negative — unhappy players "
               "the star average alone would miss.")
    if not hidden.empty:
        top = explode_topics(hidden)["topic_label"].value_counts().head(3)
        st.markdown("**Most common topics in them:**")
        for label, n in top.items():
            st.markdown(f"- {label} ({n})")
