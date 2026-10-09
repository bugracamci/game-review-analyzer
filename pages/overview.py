"""Overview: how players feel about each game and what they talk about."""
import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components import analysis_data
from ui.data import (HEATMAP_SCALE, SENTIMENT_COLORS, SENTIMENT_ORDER, explode_topics,
                     games_table, style_fig)

user, df, scheme = analysis_data(
    "What do players love and hate?",
    "Competing mobile games compared through their latest Google Play reviews, labeled by AI.")
labels = scheme["labels"]
games_info = games_table(include_hidden=True).set_index("name")

if not user:
    st.info("👋 **New here?** Pick games in the sidebar to compare them. Sign in (free) to add "
            "any Google Play game, export the data and save comparisons.")

# --- KPI cards per game ---------------------------------------------------------
st.subheader("At a glance")
groups = list(df.groupby("game"))
for start in range(0, len(groups), 4):
    cols = st.columns(4)
    for col, (game, g) in zip(cols, groups[start:start + 4]):
        store = games_info["avg_rating"].get(game) if game in games_info.index else None
        with col.container(border=True):
            st.markdown(f"**{game}**")
            st.metric("Positive reviews", f"{(g['sentiment'] == 'positive').mean():.0%}")
            st.metric("Negative reviews", f"{(g['sentiment'] == 'negative').mean():.0%}")
            st.caption(f"{len(g)} reviews · sample avg {g['rating'].mean():.1f}★"
                       + (f" · store {store:.1f}★" if store is not None and pd.notna(store) else ""))

# --- Sentiment by game ----------------------------------------------------------
st.subheader("Sentiment by game")
sent = df.groupby("game")["sentiment"].value_counts(normalize=True).rename("share").reset_index()
fig = px.bar(sent, y="game", x="share", color="sentiment", orientation="h",
             category_orders={"sentiment": SENTIMENT_ORDER},
             color_discrete_map=SENTIMENT_COLORS, text_auto=".0%",
             labels={"share": "Share of reviews", "game": ""})
fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2,
                  hovertemplate="%{y}<br>%{fullData.name}: %{x:.0%}<extra></extra>")
fig.update_xaxes(tickformat=".0%", range=[0, 1])
st.plotly_chart(style_fig(fig, 80 + 60 * sent["game"].nunique()), width="stretch")
st.caption("Sentiment is judged from the review text, not the star rating.")

# --- Topic heatmap --------------------------------------------------------------
st.subheader("What players talk about")
view = st.radio("Reviews", ["All reviews", "Negative reviews only", "Positive reviews only"],
                horizontal=True, label_visibility="collapsed")
subset = {"All reviews": df,
          "Negative reviews only": df[df["sentiment"] == "negative"],
          "Positive reviews only": df[df["sentiment"] == "positive"]}[view]
if subset.empty:
    st.info("No reviews in this group.")
else:
    topics = explode_topics(subset, labels)
    counts = subset.groupby("game").size()
    share = (topics.groupby(["topic_label", "game"]).size().unstack(fill_value=0)
             .div(counts, axis=1).reindex(list(labels.values())).fillna(0))
    fig = px.imshow(share, text_auto=".0%", aspect="auto", color_continuous_scale=HEATMAP_SCALE,
                    zmin=0, labels={"x": "", "y": "", "color": "Share"})
    fig.update_traces(hovertemplate="%{x}<br>%{y}: %{z:.0%} of reviews<extra></extra>")
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(style_fig(fig, 120 + 38 * len(labels)), width="stretch")
    st.caption("Share of reviews mentioning each topic (a review can mention up to 3 topics, "
               "so columns can add up to more than 100%).")

# --- Stars vs sentiment ---------------------------------------------------------
st.subheader("Stars vs. what the text says")
left, right = st.columns([2, 1])
with left:
    star = df.groupby("rating")["sentiment"].value_counts(normalize=True).rename("share").reset_index()
    fig = px.bar(star, x="rating", y="share", color="sentiment",
                 category_orders={"sentiment": SENTIMENT_ORDER},
                 color_discrete_map=SENTIMENT_COLORS,
                 labels={"rating": "Star rating", "share": "Share of reviews"})
    fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2,
                      hovertemplate="%{x}★ · %{fullData.name}: %{y:.0%}<extra></extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(tickvals=[1, 2, 3, 4, 5], ticktext=["1★", "2★", "3★", "4★", "5★"])
    st.plotly_chart(style_fig(fig, 360), width="stretch")
with right:
    high = df[df["rating"] >= 4]
    hidden = high[high["sentiment"] == "negative"]
    st.metric("Hidden complaints", f"{len(hidden) / max(len(high), 1):.0%}",
              help="4-5★ reviews whose text is negative.")
    st.caption("4–5★ reviews whose text is actually negative — unhappy players "
               "the star average alone would miss.")
    if not hidden.empty:
        st.markdown("**Most common topics in them:**")
        for label, n in explode_topics(hidden, labels)["topic_label"].value_counts().head(3).items():
            st.markdown(f"- {label} ({n})")
