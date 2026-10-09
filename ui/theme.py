"""Design "B · Night Radar": colors, fonts, global CSS, Plotly template and small
HTML building blocks (scoreboard, heatmap, cards) shared by every page.

All dynamic text that goes into HTML is escaped with esc(), because game names,
reviews and LLM output come from outside the app.
"""
from html import escape

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --- Palette -------------------------------------------------------------------
BG = "#0A0E16"
PANEL = "#111827"
PANEL_2 = "#131C2B"
BORDER = "#1E2838"
BORDER_2 = "#2A3650"
INK = "#E7ECF4"
INK_2 = "#C9D2E0"
MUTED = "#8A95A8"
ACCENT = "#7CE3A0"          # radar green
ACCENT_INK = "#062012"      # text on the accent
AMBER = "#FFB547"
NEG = "#FF6B5B"
NEG_TEXT = "#FF8A7D"
NEU = "#3A4559"
POS = "#5B9CFF"

GAME_COLORS = ["#7CA6FF", "#FFB547", "#7CE3A0", "#D2A8FF", "#FF8FB1", "#5FD4D4", "#C3E88D",
               "#F78C6C"]
SENTIMENT_COLORS = {"negative": NEG, "neutral": NEU, "positive": POS}
HEATMAP_SCALE = [[0, "#141E2E"], [1, ACCENT]]

FONTS_URL = ("https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700"
             "&family=JetBrains+Mono:wght@500;700&family=Figtree:wght@400;500;600;700&display=swap")


def esc(value) -> str:
    return escape("" if value is None else str(value))


# --- Global CSS ------------------------------------------------------------------
CSS = f"""
<style>
@import url('{FONTS_URL}');
html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
  font-family: 'Figtree', sans-serif;
}}
.stApp {{ background: {BG}; }}
h1, h2, h3, h4 {{ font-family: 'Sora', sans-serif !important; letter-spacing: -0.4px; }}
h1 {{ font-size: 2.4rem !important; }}
code, .mono {{ font-family: 'JetBrains Mono', monospace !important; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; max-width: 1280px; }}

/* Sidebar = left rail */
[data-testid="stSidebar"] {{ background: {BG}; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebarNav"] a {{ border-radius: 10px; min-height: 42px; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: #16223A; }}
[data-testid="stSidebarNav"] a span {{ color: #AEB8C9; font-weight: 500; }}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: #FFFFFF; }}
[data-testid="stNavSectionHeader"] {{ text-transform: uppercase; letter-spacing: 1px;
  font-size: 12px !important; color: {MUTED} !important; }}

/* Panels: every bordered container */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: {PANEL}; border-color: {BORDER} !important;
  border-radius: 16px !important; }}

/* Buttons */
.stButton button, .stDownloadButton button, .stLinkButton a, .stFormSubmitButton button {{
  border-radius: 10px; min-height: 44px; font-weight: 600; border-color: {BORDER_2};
  background: {PANEL}; color: {INK};
}}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {ACCENT} !important; color: {ACCENT_INK} !important; border-color: {ACCENT} !important;
}}
.stButton button:hover, .stDownloadButton button:hover {{ border-color: {ACCENT}; color: #FFFFFF; }}

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
  background: {PANEL} !important; border-color: {BORDER_2} !important; border-radius: 10px !important;
}}
[data-baseweb="tag"] {{ background: #16223A !important; border-radius: 999px !important; }}

/* Metrics, tabs, alerts */
[data-testid="stMetricValue"] {{ font-family: 'JetBrains Mono', monospace; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
.stTabs [aria-selected="true"] {{ color: {ACCENT} !important; }}
[data-testid="stAlert"] {{ border-radius: 12px; }}

/* Our HTML components */
.gr-eyebrow {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; color: {ACCENT};
  letter-spacing: 1px; text-transform: uppercase; }}
.gr-title, h1.gr-title {{ font-family: 'Sora', sans-serif !important; font-size: 40px !important; padding: 0 !important; font-weight: 700; line-height: 1.1;
  letter-spacing: -1px; margin: 6px 0 0; color: {INK}; }}
.gr-sub {{ color: {INK_2}; font-size: 16px; margin: 8px 0 0; line-height: 1.5; }}
.gr-panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 16px; }}
.gr-label {{ font-size: 12px; letter-spacing: 1px; text-transform: uppercase; color: {MUTED}; }}
.gr-h2, h2.gr-h2 {{ font-family: 'Sora', sans-serif !important; font-size: 20px !important; font-weight: 600 !important;
  margin: 0 !important; padding: 0 !important; line-height: 1.3 !important; color: {INK}; }}
.gr-tile {{ display: inline-flex; align-items: center; justify-content: center; border-radius: 10px;
  font-family: 'Sora', sans-serif; font-weight: 700; color: {BG}; flex: none; }}
.gr-chip {{ display: inline-flex; align-items: center; gap: 8px; border: 1px solid {BORDER_2};
  border-radius: 999px; padding: 5px 12px; font-size: 13px; color: {INK}; }}
.gr-table {{ width: 100%; border-collapse: collapse; font-size: 15px; color: {INK}; min-width: 720px; }}
.gr-table th {{ text-align: left; color: {MUTED}; font-size: 12px; letter-spacing: 1px;
  text-transform: uppercase; font-weight: 600; padding: 16px 14px; }}
.gr-table td {{ padding: 14px; border-top: 1px solid {BORDER}; vertical-align: middle; }}
.gr-bar {{ display: flex; height: 10px; border-radius: 999px; overflow: hidden; gap: 2px; }}
.gr-heat {{ display: grid; gap: 4px; min-width: 640px; }}
.gr-heat .cell {{ height: 42px; border-radius: 8px; display: flex; align-items: center;
  justify-content: center; font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; }}
.gr-quote {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 16px; padding: 20px;
  display: flex; flex-direction: column; gap: 10px; height: 100%; box-sizing: border-box; }}
.gr-quote blockquote {{ margin: 0; font-size: 15px; line-height: 1.55; color: {INK}; border: 0; padding: 0; }}
.gr-scroll {{ overflow-x: auto; }}
</style>
"""


def apply() -> None:
    """Inject fonts + CSS and make the Plotly template the default. Call once per run."""
    st.markdown(CSS, unsafe_allow_html=True)
    if "radar" not in pio.templates:
        pio.templates["radar"] = go.layout.Template(layout=dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Figtree, sans-serif", color=INK_2, size=13),
            colorway=GAME_COLORS,
            xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
            yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
            hoverlabel=dict(bgcolor=PANEL_2, bordercolor=BORDER_2, font=dict(color=INK)),
            legend=dict(font=dict(color=INK_2)),
        ))
    pio.templates.default = "radar"


def html(markup: str, where=None) -> None:
    (where or st).markdown(markup, unsafe_allow_html=True)


# --- Building blocks ---------------------------------------------------------------
def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    html(f'<div style="margin-bottom:8px"><div class="gr-eyebrow">{esc(eyebrow)}</div>'
         f'<h1 class="gr-title">{esc(title)}</h1>'
         + (f'<p class="gr-sub">{esc(subtitle)}</p>' if subtitle else "") + "</div>")


def initials(name: str) -> str:
    parts = [p for p in str(name).replace(".", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return str(name)[:2].title()


def tile(name: str, color: str, size: int = 36) -> str:
    return (f'<span class="gr-tile" style="width:{size}px;height:{size}px;background:{color};'
            f'font-size:{max(11, size // 3)}px">{esc(initials(name))}</span>')


def sentiment_bar(neg: float, neu: float, pos: float, height: int = 10) -> str:
    return (f'<div class="gr-bar" style="height:{height}px" aria-label="Sentiment split">'
            f'<span style="background:{NEG};width:{neg:.1%}"></span>'
            f'<span style="background:{NEU};width:{neu:.1%}"></span>'
            f'<span style="background:{POS};width:{pos:.1%}"></span></div>')


def scoreboard(rows: list[dict]) -> None:
    """rows: name, dev, color, neg, neu, pos (0-1), store, top, top_pct."""
    body = ""
    for r in rows:
        store = f"{r['store']:.1f}★" if r.get("store") else "–"
        top = (f'<span class="gr-chip">{esc(r["top"])} <span class="mono" style="color:{AMBER}">'
               f'{r["top_pct"]:.0%}</span></span>') if r.get("top") else ""
        body += (f'<tr><td><div style="display:flex;align-items:center;gap:12px">{tile(r["name"], r["color"])}'
                 f'<div><div style="font-weight:600">{esc(r["name"])}</div>'
                 f'<div style="font-size:13px;color:{MUTED}">{esc(r.get("dev") or "")}</div></div></div></td>'
                 f'<td style="width:34%">{sentiment_bar(r["neg"], r["neu"], r["pos"])}</td>'
                 f'<td class="mono" style="text-align:right;font-size:22px;font-weight:700;color:{NEG_TEXT}">'
                 f'{r["neg"]:.0%}</td>'
                 f'<td class="mono" style="text-align:right;color:{INK_2}">{store}</td>'
                 f'<td>{top}</td></tr>')
    html(f'<div class="gr-panel gr-scroll"><table class="gr-table"><thead><tr>'
         f'<th scope="col" style="padding-left:20px">Game</th><th scope="col">Sentiment</th>'
         f'<th scope="col" style="text-align:right">Negative</th><th scope="col" style="text-align:right">Store</th>'
         f'<th scope="col">Top complaint</th></tr></thead><tbody>{body}</tbody></table>'
         f'<div style="display:flex;gap:18px;padding:12px 20px;border-top:1px solid {BORDER};font-size:13px;color:{MUTED}">'
         f'<span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:{NEG}"></span> Negative</span>'
         f'<span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:{NEU}"></span> Neutral</span>'
         f'<span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:{POS}"></span> Positive</span>'
         f'<span style="margin-left:auto">Sentiment is judged from the review text, not the stars.</span></div></div>')


def stat_card(label: str, title: str, text: str, warm: bool = False, mono_title: bool = False,
              min_height: int = 228) -> str:
    style = (f"border-color:#5A4520;background:#17140C" if warm else "")
    label_color = "#E0B867" if warm else MUTED
    title_html = (f'<div class="mono" style="font-size:34px;font-weight:700;color:{AMBER};margin-top:4px">{esc(title)}</div>'
                  if mono_title else
                  f'<div style="font-family:Sora,sans-serif;font-size:21px;font-weight:600;margin-top:8px;color:{INK}">{esc(title)}</div>')
    return (f'<div class="gr-panel" style="padding:22px;min-height:{min_height}px;box-sizing:border-box;{style}">'
            f'<span class="gr-label" style="color:{label_color}">{esc(label)}</span>{title_html}'
            f'<p style="margin:6px 0 0;color:{"#D9CDB0" if warm else INK_2};font-size:14px;line-height:1.5">{esc(text)}</p></div>')


def heatmap(share, games: list[str]) -> None:
    """share: DataFrame index=topic labels, columns=game names, values 0-1."""
    top = max(float(share.values.max()), 0.01)
    cols = f"190px repeat({len(games)}, minmax(0, 1fr))"
    cells = '<span></span>' + "".join(
        f'<span style="font-size:13px;color:#AEB8C9;text-align:center;padding-bottom:6px">{esc(g)}</span>'
        for g in games)
    for topic, row in share.iterrows():
        cells += f'<span style="font-size:14px;color:{INK};display:flex;align-items:center">{esc(topic)}</span>'
        for g in games:
            v = float(row.get(g, 0) or 0)
            t = min(v / top, 1)
            rgb = [round(a + (b - a) * t) for a, b in zip((20, 30, 46), (124, 227, 160))]
            fg = ACCENT_INK if t > 0.6 else INK
            cells += (f'<span class="cell" title="{esc(g)} · {esc(topic)}: {v:.0%}" '
                      f'style="background:rgb({rgb[0]},{rgb[1]},{rgb[2]});color:{fg}">{v:.0%}</span>')
    html(f'<div class="gr-scroll"><div class="gr-heat" style="grid-template-columns:{cols}">{cells}</div></div>')


def quote_card(text: str, game: str, meta: str, sentiment: str, topic: str) -> str:
    color = {"negative": NEG_TEXT, "positive": POS, "neutral": MUTED}.get(sentiment, MUTED)
    return (f'<figure class="gr-quote" style="margin:0"><span class="mono" style="font-size:12px;color:{color};'
            f'letter-spacing:0.5px">{esc(sentiment.upper())} · {esc(topic.upper())}</span>'
            f'<blockquote>“{esc(text)}”</blockquote>'
            f'<figcaption style="margin-top:auto;font-size:13px;color:{MUTED}">{esc(game)} · {esc(meta)}</figcaption></figure>')


def section(title: str, step: int | None = None, subtitle: str = "") -> None:
    """Section heading in the page style; optional numbered step badge (01, 02...)."""
    badge = (f'<span class="mono" style="font-size:12px;color:{ACCENT};border:1px solid #24543A;'
             f'background:#0F1C17;border-radius:6px;padding:2px 7px;margin-right:10px;'
             f'vertical-align:3px">{step:02d}</span>' if step else "")
    html(f'<div style="margin:18px 0 4px"><h2 class="gr-h2">{badge}{esc(title)}</h2>'
         + (f'<p class="gr-sub" style="font-size:14px;margin-top:4px">{esc(subtitle)}</p>' if subtitle else "")
         + "</div>")


def kpis(items: list[tuple[str, str]]) -> None:
    """A row of number tiles (label, value) - replaces st.metric with the page style."""
    cells = "".join(
        f'<div class="gr-panel" style="padding:16px 18px"><div class="gr-label">{esc(label)}</div>'
        f'<div class="mono" style="font-size:28px;font-weight:700;color:{INK};margin-top:6px">'
        f'{esc(value)}</div></div>' for label, value in items)
    html(f'<div style="display:grid;grid-template-columns:repeat({len(items)},minmax(0,1fr));'
         f'gap:12px;margin:8px 0">{cells}</div>')


def pills(items: list[tuple[str, str, bool]]) -> None:
    """Compact status pills: (label, value, ok). ok=False shows the value in amber."""
    parts = []
    for label, value, ok in items:
        color = ACCENT if ok else AMBER
        parts.append(f'<span class="gr-chip" style="padding:6px 12px"><span style="color:{MUTED}">'
                     f'{esc(label)}</span><span class="mono" style="color:{color};font-weight:700">'
                     f'{esc(value)}</span></span>')
    html(f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 8px">{"".join(parts)}</div>')


def style_fig(fig, height: int = 380):
    # Generous margins + automargin so tick labels and axis titles never get clipped.
    tick = dict(family="Figtree, Arial, sans-serif", color=INK_2, size=12)
    title = dict(family="Figtree, Arial, sans-serif", color=MUTED, size=12)
    fig.update_layout(template="radar", height=height, margin=dict(l=56, r=12, t=40, b=48),
                      font=dict(family="Figtree, Arial, sans-serif", color=INK_2, size=13),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      bargap=0.25)
    fig.update_xaxes(showgrid=False, automargin=True, tickfont=tick, title_font=title,
                     title_standoff=12)
    fig.update_yaxes(automargin=True, tickfont=tick, title_font=title, title_standoff=12)
    return fig
