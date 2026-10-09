"""Trends: how sentiment moves over time and across app versions."""
import plotly.express as px
import streamlit as st

from config import TOPIC_LABELS
from dashboard_data import (explode_topics, filtered_reviews, game_color_map, load_reviews,
                            style_fig)

MIN_REVIEWS = 10  # periods with fewer reviews are too noisy to show

st.title("Trends over time")
st.caption("Each game's sample is its latest 400 reviews, so busier games cover a shorter period.")

df = filtered_reviews().dropna(subset=["review_date"])
if df.empty:
    st.info("Select at least one game in the sidebar.")
    st.stop()
colors = game_color_map(load_reviews()["game"].unique())

c1, c2 = st.columns(2)
period = c1.radio("Group by", ["Week", "Month"], horizontal=True)
topic_options = ["Any topic"] + [TOPIC_LABELS[t] for t in TOPIC_LABELS]
topic = c2.selectbox("Only reviews about", topic_options)

data = df
if topic != "Any topic":
    data = explode_topics(df)
    data = data[data["topic_label"] == topic]

freq = "W" if period == "Week" else "M"
data = data.assign(period=data["review_date"].dt.tz_convert(None).dt.to_period(freq).dt.start_time)
trend = (data.groupby(["game", "period"])
             .agg(reviews=("review_id", "size"),
                  negative=("sentiment", lambda s: (s == "negative").mean()))
             .reset_index())
trend = trend[trend["reviews"] >= MIN_REVIEWS]

st.subheader(f"Share of negative reviews per {period.lower()}")
if trend.empty:
    st.info(f"Not enough data: every {period.lower()} has fewer than {MIN_REVIEWS} reviews. "
            "Try grouping by month or picking another topic.")
else:
    fig = px.line(trend, x="period", y="negative", color="game", markers=True,
                  color_discrete_map=colors, custom_data=["reviews"],
                  labels={"period": "", "negative": "Negative share", "game": ""})
    fig.update_traces(line_width=2, marker_size=8,
                      hovertemplate="%{x|%b %d, %Y}<br>Negative: %{y:.0%}"
                                    "<br>%{customdata[0]} reviews<extra>%{fullData.name}</extra>")
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style_fig(fig, 400), use_container_width=True)
    st.caption(f"Periods with fewer than {MIN_REVIEWS} reviews are hidden.")

# --- By app version: did an update make players angry? -----------------------
st.subheader("Sentiment by app version")
game = st.selectbox("Game", sorted(df["game"].unique()))
g = df[(df["game"] == game) & df["version"].notna()]
by_version = (g.groupby("version")
                .agg(reviews=("review_id", "size"),
                     negative=("sentiment", lambda s: (s == "negative").mean()),
                     first_seen=("review_date", "min"))
                .reset_index())
by_version = by_version[by_version["reviews"] >= MIN_REVIEWS].sort_values("first_seen")
if by_version.empty:
    st.info("Not enough reviews per version for this game.")
else:
    fig = px.bar(by_version, x="version", y="negative", custom_data=["reviews"],
                 labels={"version": "App version (ordered by release)", "negative": "Negative share"},
                 color_discrete_sequence=[colors.get(game, "#2a78d6")])
    fig.update_traces(hovertemplate="v%{x}<br>Negative: %{y:.0%}<br>%{customdata[0]} reviews"
                                    "<extra></extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(type="category")
    st.plotly_chart(style_fig(fig, 340), use_container_width=True)
    st.caption("A jump after a version points to an update worth checking (balance change, "
               "new monetization, bugs). Versions with fewer than "
               f"{MIN_REVIEWS} reviews are hidden.")
