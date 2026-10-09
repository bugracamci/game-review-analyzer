"""Overview: scoreboard, key signals, topic radar and real quotes for the selected games."""
import pandas as pd
import plotly.express as px
import streamlit as st

from ui import theme
from ui.components import analysis_data
from ui.data import SENTIMENT_COLORS, SENTIMENT_ORDER, color_map, explode_topics, games_table

user, df, scheme = analysis_data(
    "What players love and hate",
    "Competing mobile games compared through their latest Google Play reviews, labeled by AI.")
labels = scheme["labels"]
info = games_table(include_hidden=True).set_index("app_id")
names = sorted(df["game"].unique())
colors = color_map(names)

# --- Scoreboard ------------------------------------------------------------------------
rows, top_by_game = [], {}
for game, g in df.groupby("game"):
    share = g["sentiment"].value_counts(normalize=True)
    neg = g[g["sentiment"] == "negative"]
    top, top_pct = None, 0.0
    if not neg.empty:
        counts = explode_topics(neg, labels)["topic_label"].value_counts() / len(neg)
        counts = counts.drop(labels.get("other", "Other"), errors="ignore")
        if not counts.empty:
            top, top_pct = counts.index[0], float(counts.iloc[0])
    top_by_game[game] = top
    app = g["app_id"].iloc[0]
    store = info["avg_rating"].get(app) if app in info.index else None
    rows.append({"name": game, "dev": info["developer"].get(app) if app in info.index else "",
                 "color": colors.get(game, theme.GAME_COLORS[0]),
                 "neg": share.get("negative", 0), "neu": share.get("neutral", 0),
                 "pos": share.get("positive", 0),
                 "store": float(store) if store is not None and pd.notna(store) else None,
                 "top": top, "top_pct": top_pct})
rows.sort(key=lambda r: -r["neg"])
theme.scoreboard(rows)

# --- Three signals ------------------------------------------------------------------------
pos_df = df[df["sentiment"] == "positive"]
loved, loved_text = "–", "Not enough positive reviews."
if not pos_df.empty:
    per_game = (explode_topics(pos_df, labels).groupby(["game", "topic_label"]).size()
                / pos_df.groupby("game").size()).rename("share").reset_index()
    best = per_game.groupby("topic_label")["share"].mean().sort_values(ascending=False)
    loved = best.index[0]
    rng = per_game[per_game["topic_label"] == loved]["share"]
    loved_text = (f"Mentioned in {rng.min():.0%}–{rng.max():.0%} of positive reviews per game."
                  if len(rng) > 1 else f"Mentioned in {rng.iloc[0]:.0%} of positive reviews.")

tops = pd.Series({k: v for k, v in top_by_game.items() if v})
if tops.nunique() >= 2:
    a, b = tops.value_counts().index[:2]
    split_title = f"{a} vs. {b}"
    split_text = (f"{', '.join(tops[tops == a].index)} lose players to {a.lower()}; "
                  f"{', '.join(tops[tops == b].index)} to {b.lower()}.")
elif tops.nunique() == 1:
    split_title, split_text = tops.iloc[0], "The #1 complaint is the same for every selected game."
else:
    split_title, split_text = "–", "Not enough negative reviews."

high = df[df["rating"] >= 4]
hidden = high[high["sentiment"] == "negative"]
hidden_share = len(hidden) / max(len(high), 1)
hidden_topic = (explode_topics(hidden, labels)["topic_label"].value_counts().index[0]
                if not hidden.empty else None)

c1, c2, c3 = st.columns(3)
with c1:
    theme.html(theme.stat_card("Most loved", loved, loved_text))
with c2:
    theme.html(theme.stat_card("Biggest difference", split_title, split_text))
with c3:
    theme.html(theme.stat_card(
        "Hidden complaints", f"{hidden_share:.0%}" if len(high) else "–",
        ("of 4–5★ reviews are negative in text"
         + (f", mostly about {hidden_topic.lower()}." if hidden_topic else "."))
        if len(high) else "No 4–5★ reviews with the current filters.",
        warm=True, mono_title=True))

# --- Topic radar (heatmap) ------------------------------------------------------------------
with st.container(border=True):
    left, right = st.columns([3, 2], vertical_alignment="center")
    view = right.segmented_control("Reviews", ["All", "Negative", "Positive"], default="Negative",
                                   label_visibility="collapsed", key="heat_view") or "Negative"
    left.markdown(f'<h2 class="gr-h2">Topic radar · {theme.esc(view.lower())} reviews</h2>',
                  unsafe_allow_html=True)
    subset = df if view == "All" else df[df["sentiment"] == view.lower()]
    if subset.empty:
        st.info("No reviews in this group.")
    else:
        topics = explode_topics(subset, labels)
        share = (topics.groupby(["topic_label", "game"]).size().unstack(fill_value=0)
                 .div(subset.groupby("game").size(), axis=1)
                 .reindex(list(labels.values())).fillna(0))
        theme.heatmap(share, [g for g in names if g in share.columns])
        st.caption("Share of reviews mentioning each topic. A review can mention up to 3 topics.")

# --- Real quotes ------------------------------------------------------------------------------
neg = df[(df["sentiment"] == "negative") & (df["content"].str.len() > 40)]
if not neg.empty:
    st.markdown('<h2 class="gr-h2" style="margin-top:8px">What players actually say</h2>',
                unsafe_allow_html=True)
    picks = (neg.sort_values(["thumbs_up", "rating"], ascending=[False, True])
             .groupby("game").head(1).head(3))
    for col, (_, r) in zip(st.columns(3), picks.iterrows()):
        topic = labels.get(r["topics"][0], r["topics"][0]) if r["topics"] else ""
        meta = f"{int(r['rating'])}★" + (f" · {int(r['thumbs_up'])} found helpful" if r["thumbs_up"] else "")
        text = r["content"] if len(r["content"]) <= 220 else r["content"][:217].rsplit(" ", 1)[0] + "…"
        with col:
            theme.html(theme.quote_card(text, r["game"], meta, "negative", topic))
    st.page_link("pages/explorer.py", label="Open the review explorer", icon=":material/arrow_forward:")

# --- Stars vs text ------------------------------------------------------------------------------
with st.container(border=True):
    st.markdown('<h2 class="gr-h2">Stars vs. what the text says</h2>', unsafe_allow_html=True)
    star = df.groupby("rating")["sentiment"].value_counts(normalize=True).rename("share").reset_index()
    fig = px.bar(star, x="rating", y="share", color="sentiment",
                 category_orders={"sentiment": SENTIMENT_ORDER},
                 color_discrete_map=SENTIMENT_COLORS,
                 labels={"rating": "Star rating", "share": "Share of reviews"})
    fig.update_traces(marker_line_width=0,
                      hovertemplate="%{x}★ · %{fullData.name}: %{y:.0%}<extra></extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(tickvals=[1, 2, 3, 4, 5], ticktext=["1★", "2★", "3★", "4★", "5★"])
    st.plotly_chart(theme.style_fig(fig, 340), width="stretch", theme=None)

if not user:
    theme.html(f'<div class="gr-panel" style="padding:24px;display:flex;flex-wrap:wrap;gap:16px;'
               f'align-items:center;justify-content:space-between;border-color:#24543A;background:#0F1C17">'
               f'<div><div class="gr-h2">Compare your own competitors</div>'
               f'<p class="gr-sub" style="margin-top:6px">Sign in with Google, paste any Google Play link '
               f'and label its reviews with your own free Gemini key.</p></div></div>')
