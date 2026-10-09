"""Review Explorer: read real examples behind every number."""
import pandas as pd
import streamlit as st

from config import SENTIMENTS, TOPIC_LABELS
from dashboard_data import explode_topics, filtered_reviews

st.title("Review Explorer")
st.caption("Pick a topic and see what players actually wrote.")

df = filtered_reviews()
if df.empty:
    st.info("Select at least one game in the sidebar.")
    st.stop()

c1, c2, c3 = st.columns(3)
topic = c1.selectbox("Topic", [TOPIC_LABELS[t] for t in TOPIC_LABELS])
sentiments = c2.multiselect("Sentiment", SENTIMENTS, default=["negative"])
stars = c3.slider("Stars", 1, 5, (1, 5))

rows = explode_topics(df)
rows = rows[(rows["topic_label"] == topic)
            & rows["sentiment"].isin(sentiments)
            & rows["rating"].between(*stars)]

st.markdown(f"**{len(rows)} reviews match.** Most-liked and most detailed first.")
rows = rows.assign(length=rows["content"].str.len()).sort_values(
    ["thumbs_up", "length"], ascending=False)

tabs = st.tabs(sorted(rows["game"].unique()) or ["No matches"])
for tab, game in zip(tabs, sorted(rows["game"].unique())):
    with tab:
        for _, r in rows[rows["game"] == game].head(8).iterrows():
            with st.container(border=True):
                meta = f"{'★' * int(r['rating'])} · {r['sentiment']}"
                if pd.notna(r["thumbs_up"]) and r["thumbs_up"]:
                    meta += f" · 👍 {int(r['thumbs_up'])}"
                if pd.notna(r["version"]) and r["version"]:
                    meta += f" · v{r['version']}"
                st.caption(meta)
                st.write(r["content"])
                if pd.notna(r["feature_request"]) and r["feature_request"]:
                    st.markdown(f"💡 *Feature request:* {r['feature_request']}")

st.divider()
st.subheader("Feature requests")
st.caption("Short summaries written by the LLM for every review that asks for something.")
requests_df = df[df["feature_request"].notna()][["game", "rating", "feature_request", "thumbs_up"]]
requests_df = requests_df.sort_values(["game", "thumbs_up"], ascending=[True, False])
st.dataframe(
    requests_df.rename(columns={"game": "Game", "rating": "Stars",
                                "feature_request": "Request", "thumbs_up": "👍"}),
    hide_index=True, use_container_width=True, height=360,
)
