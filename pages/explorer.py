"""Review Explorer: read real examples behind every number."""
import pandas as pd
import streamlit as st

from config import SENTIMENTS
from ui.components import analysis_data, export_buttons
from ui.data import explode_topics

user, df, scheme = analysis_data("Review Explorer",
                                 "Pick a topic and see what players actually wrote.")
labels = scheme["labels"]

c1, c2, c3 = st.columns(3)
topic = c1.selectbox("Topic", list(labels.values()))
sentiments = c2.multiselect("Sentiment", SENTIMENTS, default=["negative"])
stars = c3.slider("Stars", 1, 5, (1, 5))
search = st.text_input("Search in review text (optional)", placeholder="e.g. energy, ads, crash")

rows = explode_topics(df, labels)
rows = rows[(rows["topic_label"] == topic)
            & rows["sentiment"].isin(sentiments)
            & rows["rating"].between(*stars)]
if search.strip():
    rows = rows[rows["content"].str.contains(search.strip(), case=False, regex=False, na=False)]

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
    hide_index=True, width="stretch", height=360,
)

st.divider()
st.subheader("Download")
export_buttons(user, df, labels, "selected-games")
