"""Step 3 - Ask the LLM for a short LiveOps / UA brief based on the labeled data.

Numbers are computed here with pandas (exact), and the LLM only interprets
them plus a few real quotes. This keeps the brief grounded: the model is told
to use only the numbers it is given. The result is saved in the `insights`
table, so the dashboard shows it without calling the API.

Usage:  python generate_insights.py
"""
import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd

import config
from db import connect
from llm_client import complete_json, model_name

SYSTEM_PROMPT = """You are a senior mobile games analyst writing for a LiveOps and
user-acquisition (UA) team. You get statistics computed from labeled Google Play
reviews of competing survivor-like / arena games, plus real review quotes.

Rules:
- Use ONLY the numbers given. Quote them exactly (e.g. "38% of negative reviews").
- Be specific and practical. No generic advice like "listen to players".
- Compare games with each other: the value is in the differences.
- Keep every bullet under 30 words. Answer in English, ONLY with JSON:
{
  "headline": "one sentence with the single most important finding",
  "key_findings": [{"finding": "...", "evidence": "numbers that support it"}],
  "games": [{"game": "...", "players_love": ["..."], "players_complain_about": ["..."],
             "top_requests": ["..."]}],
  "liveops_actions": [{"game": "...", "action": "...", "why": "..."}],
  "ua_angles": [{"angle": "ad creative or targeting idea", "why": "..."}],
  "new_game_opportunities": ["gaps a NEW survivor-like game could win on"]
}
Give 4-6 key_findings, 3 items per list in games, 4-6 liveops_actions,
3-4 ua_angles and 3-4 new_game_opportunities."""


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(config.DB_PATH) as conn:
        reviews = pd.read_sql_query(
            """SELECT g.name AS game, r.rating, r.content, r.thumbs_up,
                      c.sentiment, c.topics, c.feature_request
               FROM reviews r JOIN games g ON g.app_id = r.app_id
               JOIN classifications c ON c.review_id = r.review_id""", conn)
        games = pd.read_sql_query("SELECT * FROM games", conn)
    reviews["topics"] = reviews["topics"].apply(json.loads)
    return reviews, games


def topic_shares(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    shares = df.explode("topics")["topics"].value_counts() / len(df)
    return {config.TOPIC_LABELS[t]: f"{v:.0%}" for t, v in shares.head(5).items()}


def build_stats(reviews: pd.DataFrame, games: pd.DataFrame) -> list[dict]:
    stats = []
    for game, g in reviews.groupby("game"):
        info = games[games["name"] == game].iloc[0]
        neg, pos = g[g["sentiment"] == "negative"], g[g["sentiment"] == "positive"]
        high = g[g["rating"] >= 4]
        liked = g.assign(length=g["content"].str.len()).sort_values(
            ["thumbs_up", "length"], ascending=False)
        stats.append({
            "game": game,
            "developer": info["developer"],
            "price": "free" if not info["price"] else f"${info['price']}",
            "installs": info["installs"],
            "store_rating": round(float(info["avg_rating"] or 0), 2),
            "reviews_analyzed": len(g),
            "avg_stars_in_sample": round(g["rating"].mean(), 2),
            "positive_share": f"{len(pos) / len(g):.0%}",
            "negative_share": f"{len(neg) / len(g):.0%}",
            "hidden_complaints_share_of_4_5_star": f"{(high['sentiment'] == 'negative').mean():.0%}"
                                                  if len(high) else "n/a",
            "topics_in_positive_reviews": topic_shares(pos),
            "topics_in_negative_reviews": topic_shares(neg),
            "feature_requests": liked["feature_request"].dropna().drop_duplicates().head(25).tolist(),
            "top_negative_quotes": [q[:250] for q in liked[liked["sentiment"] == "negative"]
                                    ["content"].head(5)],
            "top_positive_quotes": [q[:250] for q in liked[liked["sentiment"] == "positive"]
                                    ["content"].head(3)],
        })
    return stats


def main():
    reviews, games = load()
    if reviews.empty:
        raise SystemExit("No labeled reviews yet - run classify_reviews.py first.")
    stats = build_stats(reviews, games)
    print(f"Asking {model_name()} for insights on {len(stats)} games...")
    answer = complete_json(SYSTEM_PROMPT, json.dumps(stats, ensure_ascii=False, indent=1))
    answer["games_compared"] = [s["game"] for s in stats]
    answer["reviews_analyzed"] = int(len(reviews))

    conn = connect()
    conn.execute("INSERT INTO insights (created_at, model, content) VALUES (?, ?, ?)",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"), model_name(),
                  json.dumps(answer, ensure_ascii=False)))
    conn.commit()
    print("Saved. Headline:", answer.get("headline"))


if __name__ == "__main__":
    main()
