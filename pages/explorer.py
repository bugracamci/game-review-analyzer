"""Review Explorer: read real examples behind every number."""
import pandas as pd
import streamlit as st

from config import SENTIMENTS
from ui.components import analysis_data, export_buttons
from ui import theme
from ui.data import explode_topics

user, df, scheme = analysis_data("Review Explorer",
                                 "Pick a topic and see what players actually wrote.")
labels = scheme["labels"]

c1, c2 = st.columns(2)
topic = c1.selectbox("Topic", list(labels.values()))
sentiments = c2.multiselect("Sentiment", SENTIMENTS, default=["negative"])
search = st.text_input("Search in review text (optional)", placeholder="e.g. energy, ads, crash")

rows = explode_topics(df, labels)
rows = rows[(rows["topic_label"] == topic)
            & rows["sentiment"].isin(sentiments)]
if search.strip():
    rows = rows[rows["content"].str.contains(search.strip(), case=False, regex=False, na=False)]

st.caption(f"{len(rows)} reviews match · most-liked and most detailed first")
rows = rows.assign(length=rows["content"].str.len()).sort_values(
    ["thumbs_up", "length"], ascending=False)

tabs = st.tabs(sorted(rows["game"].unique()) or ["No matches"])
for tab, game in zip(tabs, sorted(rows["game"].unique())):
    with tab:
        game_rows = rows[rows["game"] == game].head(9)
        cols = st.columns(3)  # masonry: card i goes to column i % 3, so no row gaps
        for i, (_, r) in enumerate(game_rows.iterrows()):
            meta = f"{int(r['rating'])}★"
            if pd.notna(r["thumbs_up"]) and r["thumbs_up"]:
                meta += f" · {int(r['thumbs_up'])} found helpful"
            if pd.notna(r["version"]) and r["version"]:
                meta += f" · v{r['version']}"
            card = theme.quote_card(r["content"], game, meta, r["sentiment"], topic)
            if pd.notna(r["feature_request"]) and r["feature_request"]:
                card = card.replace("</figure>", f'<div style="font-size:13px;color:#FFB547">'
                                                 f'Request: {theme.esc(r["feature_request"])}</div></figure>')
            with cols[i % 3]:
                theme.html(card)

st.markdown('<h2 class="gr-h2" style="margin-top:12px">Feature requests</h2>', unsafe_allow_html=True)
st.caption("Short summaries written by the LLM for every review that asks for something.")
requests_df = df[df["feature_request"].notna()][["game", "rating", "feature_request", "thumbs_up"]]
requests_df = requests_df.sort_values(["game", "thumbs_up"], ascending=[True, False])
st.dataframe(
    requests_df.rename(columns={"game": "Game", "rating": "Stars",
                                "feature_request": "Request", "thumbs_up": "Helpful"}),
    hide_index=True, width="stretch", height=360,
)

st.markdown('<h2 class="gr-h2" style="margin-top:12px">Download</h2>', unsafe_allow_html=True)
export_buttons(user, df, labels, "selected-games")
