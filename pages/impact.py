"""Before vs. after: did an update change what players complain about?"""
import re

import pandas as pd
import streamlit as st

from ui import theme
from ui.components import analysis_data
from ui.data import explode_topics

MIN_REVIEWS = 10   # fewer reviews than this per side is too noisy to compare
SMALL_SAMPLE = 30  # below this we warn that percentages swing a lot

user, df, scheme = analysis_data(
    "Before vs. after an update",
    "Pick a game and two app versions – or an update date – to see what changed in what "
    "players say.")
labels = scheme["labels"]
E = theme.esc


def version_key(v: str) -> tuple:
    """Sort '1.10.2' after '1.9.0' (natural version order)."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-_ ]", str(v)))


c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
game = c1.selectbox("Game", sorted(df["game"].unique()))
mode = c2.segmented_control("Compare by", ["App version", "Date"], default="App version",
                            key="impact_mode") or "App version"
g = df[df["game"] == game]

if mode == "App version":
    counts = g["version"].dropna().value_counts()
    versions = sorted([v for v, n in counts.items() if n >= MIN_REVIEWS and str(v).strip()],
                      key=version_key)
    if len(versions) < 2:
        st.info(f"{game} doesn't have two app versions with at least {MIN_REVIEWS} reviews each. "
                "Try **Date** instead, or download more reviews from **All games**.")
        st.stop()
    v1, v2 = st.columns(2)
    a = v1.selectbox("Before", versions, index=len(versions) - 2,
                     format_func=lambda v: f"v{v} · {counts[v]} reviews")
    b = v2.selectbox("After", versions, index=len(versions) - 1,
                     format_func=lambda v: f"v{v} · {counts[v]} reviews")
    before, after = g[g["version"] == a], g[g["version"] == b]
    name_a, name_b = f"v{a}", f"v{b}"
else:
    dates = g["review_date"].dropna()
    if dates.empty:
        st.info("These reviews have no dates.")
        st.stop()
    lo, hi = dates.min().date(), dates.max().date()
    latest = sorted(g["version"].dropna().unique(), key=version_key)
    first_of_latest = g[g["version"] == latest[-1]]["review_date"].min() if latest else pd.NaT
    default = first_of_latest.date() if pd.notna(first_of_latest) else lo + (hi - lo) / 2
    d1, d2 = st.columns(2)
    split = d1.date_input("Update date", value=min(max(default, lo), hi), min_value=lo, max_value=hi,
                          help="Defaults to the first review of the newest app version.")
    window = d2.slider("Days on each side", 3, 60, 14)
    t = pd.Timestamp(split, tz="UTC")
    before = g[(g["review_date"] >= t - pd.Timedelta(days=window)) & (g["review_date"] < t)]
    after = g[(g["review_date"] >= t) & (g["review_date"] < t + pd.Timedelta(days=window))]
    name_a, name_b = f"{window} days before", f"{window} days after"

if len(before) < MIN_REVIEWS or len(after) < MIN_REVIEWS:
    st.info(f"Each side needs at least {MIN_REVIEWS} reviews (now {len(before)} before, "
            f"{len(after)} after). Pick other versions or a wider window.")
    st.stop()


# --- Headline numbers -------------------------------------------------------------------------
def neg_share(x: pd.DataFrame) -> float:
    return float((x["sentiment"] == "negative").mean())


def delta_html(diff: float, unit: str, lower_is_better: bool) -> str:
    if abs(diff) < (0.05 if unit == "★" else 0.5):  # below display precision
        return f'<span style="color:{theme.MUTED}">≈ same</span>'
    good = (diff < 0) == lower_is_better
    color = theme.ACCENT if good else theme.NEG_TEXT
    arrow = "▼" if diff < 0 else "▲"
    return f'<span style="color:{color}">{arrow} {abs(diff):.{1 if unit == "★" else 0}f}{unit}</span>'


neg_a, neg_b = neg_share(before), neg_share(after)
star_a, star_b = before["rating"].mean(), after["rating"].mean()
tiles = [
    ("Negative reviews", f"{neg_a:.0%}", f"{neg_b:.0%}", delta_html((neg_b - neg_a) * 100, " pts", True)),
    ("Average stars", f"{star_a:.2f}★", f"{star_b:.2f}★", delta_html(star_b - star_a, "★", False)),
    ("Reviews compared", f"{len(before)}", f"{len(after)}", ""),
]
theme.html('<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:8px 0">'
           + "".join(
               f'<div class="gr-panel" style="padding:18px 20px"><div class="gr-label">{E(lbl)}</div>'
               f'<div style="display:flex;align-items:baseline;gap:10px;margin-top:8px;flex-wrap:wrap">'
               f'<span class="mono" style="font-size:18px;color:{theme.MUTED}">{E(va)}</span>'
               f'<span style="color:{theme.MUTED}">→</span>'
               f'<span class="mono" style="font-size:30px;font-weight:700;color:{theme.INK}">{E(vb)}</span>'
               f'<span class="mono" style="font-size:14px">{d}</span></div></div>'
               for lbl, va, vb, d in tiles) + "</div>")
if min(len(before), len(after)) < SMALL_SAMPLE:
    st.caption(f"Small sample (under {SMALL_SAMPLE} reviews on one side) – percentages can swing a lot.")


# --- Complaint rate per topic ------------------------------------------------------------------
def complaint_rate(x: pd.DataFrame) -> pd.Series:
    """Share of ALL reviews in the period that are negative and mention the topic."""
    neg = explode_topics(x[x["sentiment"] == "negative"], labels)
    return neg.groupby("topic_label")["review_id"].nunique() / len(x)


rates = pd.DataFrame({"before": complaint_rate(before), "after": complaint_rate(after)}).fillna(0)
rates = rates.drop(labels.get("other", "Other"), errors="ignore")
rates["diff"] = rates["after"] - rates["before"]
rates = rates[(rates["before"] > 0) | (rates["after"] > 0)].sort_values("diff")

if not rates.empty:
    best, worst = rates.iloc[0], rates.iloc[-1]
    s1, s2 = st.columns(2)
    with s1:
        theme.html(theme.stat_card(
            "Got better", best.name if best["diff"] < 0 else "Nothing clearly improved",
            f"Complaints went from {best['before']:.0%} to {best['after']:.0%} of reviews."
            if best["diff"] < 0 else "No complaint topic dropped between the two periods.", min_height=0))
    with s2:
        theme.html(theme.stat_card(
            "Got worse", worst.name if worst["diff"] > 0 else "Nothing clearly got worse",
            f"Complaints went from {worst['before']:.0%} to {worst['after']:.0%} of reviews."
            if worst["diff"] > 0 else "No complaint topic grew between the two periods.",
            warm=worst["diff"] > 0, min_height=0))

    scale = max(rates["diff"].abs().max(), 0.01)
    rows = []
    for topic, r in rates.iterrows():
        width = abs(r["diff"]) / scale * 50
        color = theme.ACCENT if r["diff"] < 0 else theme.NEG
        bar = (f'<div style="position:relative;height:10px;background:{theme.PANEL_2};border-radius:999px">'
               f'<div style="position:absolute;top:-3px;bottom:-3px;left:50%;width:1px;background:{theme.BORDER_2}"></div>'
               f'<div style="position:absolute;top:0;bottom:0;border-radius:999px;background:{color};'
               + (f'right:50%;width:{width:.1f}%' if r["diff"] < 0 else f'left:50%;width:{width:.1f}%')
               + '"></div></div>')
        rows.append(f'<tr><td>{E(topic)}</td><td class="mono">{r["before"]:.0%}</td>'
                    f'<td class="mono">{r["after"]:.0%}</td><td style="width:38%">{bar}</td>'
                    f'<td class="mono" style="text-align:right">{delta_html(r["diff"] * 100, " pts", True)}</td></tr>')
    with st.container(border=True):
        theme.html(f'<h2 class="gr-h2">Complaints by topic</h2><p class="gr-sub" style="font-size:14px;'
                   f'margin:4px 0 12px">Share of all reviews that are negative and mention the topic · '
                   f'{E(name_a)} → {E(name_b)}</p>'
                   f'<div class="gr-scroll"><table class="gr-table"><thead><tr><th>Topic</th>'
                   f'<th>{E(name_a)}</th><th>{E(name_b)}</th><th>Change</th><th></th></tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table></div>')

    # --- What players say after -----------------------------------------------------------------
    if worst["diff"] > 0:
        key = {v: k for k, v in labels.items()}.get(worst.name)
        quotes = after[(after["sentiment"] == "negative")
                       & after["topics"].apply(lambda t: key in t)
                       & (after["content"].str.len() > 40)]
        quotes = quotes.sort_values("thumbs_up", ascending=False).head(3)
        if not quotes.empty:
            theme.section(f"What players say about {worst.name.lower()} after the change")
            for col, (_, r) in zip(st.columns(3), quotes.iterrows()):
                text = r["content"] if len(r["content"]) <= 220 else r["content"][:217].rsplit(" ", 1)[0] + "…"
                meta = f"{int(r['rating'])}★" + (f" · v{r['version']}" if pd.notna(r["version"]) else "")
                with col:
                    theme.html(theme.quote_card(text, game, meta, "negative", worst.name))
