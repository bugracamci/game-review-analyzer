"""LiveOps / UA brief for a set of games.

Numbers are computed here with pandas (exact); the LLM only interprets them
plus a few real quotes, and is told to use only the numbers it is given.
"""
import json

import pandas as pd

from core import repo
from core.db import Database
from core.llm import LLMConfig, complete_json

SYSTEM_PROMPT = """You are a senior mobile games analyst writing for a small game team
(LiveOps, user acquisition and game design). You get statistics computed from labeled
Google Play reviews of competing games, plus real review quotes.

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
  "new_game_opportunities": ["gaps a NEW game in this genre could win on"]
}
Give 4-6 key_findings, 3 items per list in games, 4-6 liveops_actions,
3-4 ua_angles and 3-4 new_game_opportunities."""


def _topic_shares(df: pd.DataFrame, labels: dict) -> dict:
    if df.empty:
        return {}
    shares = df.explode("topics")["topics"].value_counts() / len(df)
    return {labels.get(t, t): f"{v:.0%}" for t, v in shares.head(5).items()}


def build_stats(df: pd.DataFrame, games: pd.DataFrame, labels: dict) -> list[dict]:
    stats = []
    for game, g in df.groupby("game"):
        info = games[games["name"] == game]
        info = info.iloc[0] if not info.empty else {}
        neg, pos = g[g["sentiment"] == "negative"], g[g["sentiment"] == "positive"]
        high = g[g["rating"] >= 4]
        liked = g.assign(length=g["content"].str.len()).sort_values(
            ["thumbs_up", "length"], ascending=False)
        stats.append({
            "game": game,
            "developer": info.get("developer") if len(info) else None,
            "price": "free" if not (len(info) and info.get("price")) else f"${info['price']}",
            "installs": info.get("installs") if len(info) else None,
            "store_rating": round(float(info.get("avg_rating") or 0), 2) if len(info) else None,
            "reviews_analyzed": len(g),
            "avg_stars_in_sample": round(g["rating"].mean(), 2),
            "positive_share": f"{len(pos) / len(g):.0%}",
            "negative_share": f"{len(neg) / len(g):.0%}",
            "hidden_complaints_share_of_4_5_star":
                f"{(high['sentiment'] == 'negative').mean():.0%}" if len(high) else "n/a",
            "topics_in_positive_reviews": _topic_shares(pos, labels),
            "topics_in_negative_reviews": _topic_shares(neg, labels),
            "feature_requests": liked["feature_request"].dropna().drop_duplicates()
                                .head(25).tolist(),
            "top_negative_quotes": [q[:250] for q in
                                    liked[liked["sentiment"] == "negative"]["content"].head(5)],
            "top_positive_quotes": [q[:250] for q in
                                    liked[liked["sentiment"] == "positive"]["content"].head(3)],
        })
    return stats


def generate(db: Database, app_ids: list[str], scheme_id: str, llm: LLMConfig,
             user_email: str | None = None) -> dict:
    scheme = repo.get_scheme(db, scheme_id)
    df = repo.load_labeled(db, app_ids, scheme["id"])
    if df.empty:
        raise ValueError("These games have no labeled reviews yet.")
    games = repo.list_games(db, include_hidden=True)
    stats = build_stats(df, games, scheme["labels"])
    answer = complete_json(llm, SYSTEM_PROMPT, json.dumps(stats, ensure_ascii=False, indent=1))
    answer["games_compared"] = [s["game"] for s in stats]
    answer["reviews_analyzed"] = int(len(df))
    repo.save_insight(db, repo.scope_key(app_ids, scheme["id"]), user_email, llm.model, answer)
    return answer
