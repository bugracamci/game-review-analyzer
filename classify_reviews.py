"""Step 2 - Label every review with an LLM: sentiment, topics, feature request.

Reviews are sent in batches of 25 (config.BATCH_SIZE) to save API calls,
and the model must answer in a fixed JSON format. Results are saved after
every batch, so if the script stops (quota, network, Ctrl+C) just run it
again - it continues with the reviews that are not labeled yet.

Usage:
    python classify_reviews.py              # everything not yet labeled
    python classify_reviews.py --limit 50   # quick test on 50 reviews
"""
import argparse
import json
from datetime import datetime, timezone

import config
from db import connect
from llm_client import DailyQuotaExceeded, LLMError, complete_json, model_name

MAX_REVIEW_CHARS = 700  # very long reviews are cut to keep prompts small

SYSTEM_PROMPT = f"""You are a games user-research analyst. You label mobile game
Google Play reviews so a LiveOps / user-acquisition team can compare games.

For each review return:
- "sentiment": one of {config.SENTIMENTS}. Judge the TEXT, not the star rating.
- "topics": 1 to 3 topic keys from this list (use "other" only if nothing fits):
{chr(10).join(f'    "{key}": {desc}' for key, desc in config.TOPICS.items())}
- "feature_request": if the player asks for a new feature, change or content,
  summarize it in max 12 English words. Otherwise null.

Reviews may be in any language; always answer in English.
Answer ONLY with JSON in this exact shape:
{{"results": [{{"i": 1, "sentiment": "negative", "topics": ["monetization_ads"], "feature_request": null}}]}}
Return exactly one result per review, using the same "i" numbers."""


def build_prompt(batch: list) -> str:
    items = [
        {
            "i": n,
            "game": row["game"],
            "stars": row["rating"],
            "text": (row["content"] or "")[:MAX_REVIEW_CHARS],
        }
        for n, row in enumerate(batch, start=1)
    ]
    return "Label these reviews:\n" + json.dumps(items, ensure_ascii=False)


def clean_result(item: dict) -> dict | None:
    """Validate one model answer; fix small issues, reject broken ones."""
    sentiment = str(item.get("sentiment", "")).lower().strip()
    if sentiment not in config.SENTIMENTS:
        return None
    topics = [t for t in item.get("topics") or [] if t in config.TOPICS][:3]
    if not topics:
        topics = ["other"]
    request = item.get("feature_request")
    if not isinstance(request, str) or request.strip().lower() in ("", "null", "none", "n/a"):
        request = None
    return {"sentiment": sentiment, "topics": topics, "feature_request": request}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only label this many reviews")
    args = parser.parse_args()

    conn = connect()
    rows = conn.execute(
        """SELECT r.review_id, r.rating, r.content, g.name AS game
           FROM reviews r
           JOIN games g ON g.app_id = r.app_id
           LEFT JOIN classifications c ON c.review_id = r.review_id
           WHERE c.review_id IS NULL
           ORDER BY g.name, r.review_date DESC"""
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("Nothing to label - all reviews are already classified.")
        return

    batches = [rows[i:i + config.BATCH_SIZE] for i in range(0, len(rows), config.BATCH_SIZE)]
    print(f"{len(rows)} reviews to label in {len(batches)} batches "
          f"({config.LLM_PROVIDER} / {model_name()})")

    saved = 0
    for b, batch in enumerate(batches, start=1):
        try:
            answer = complete_json(SYSTEM_PROMPT, build_prompt(batch))
        except DailyQuotaExceeded as e:
            print(f"\nStopped: {e}")
            break
        except LLMError as e:
            print(f"  batch {b}: failed ({e}). Skipping; it will be retried next run.")
            continue

        by_index = {item.get("i"): item for item in answer.get("results", [])
                    if isinstance(item, dict)}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for n, row in enumerate(batch, start=1):
            result = clean_result(by_index.get(n, {}))
            if result:
                records.append((row["review_id"], result["sentiment"],
                                json.dumps(result["topics"]), result["feature_request"],
                                model_name(), now))
        conn.executemany(
            "INSERT OR REPLACE INTO classifications VALUES (?, ?, ?, ?, ?, ?)", records
        )
        conn.commit()
        saved += len(records)
        print(f"  batch {b}/{len(batches)}: {len(records)}/{len(batch)} labeled")

    left = conn.execute(
        """SELECT COUNT(*) FROM reviews r LEFT JOIN classifications c
           ON c.review_id = r.review_id WHERE c.review_id IS NULL"""
    ).fetchone()[0]
    print(f"\nDone: {saved} labeled this run, {left} still unlabeled.")


if __name__ == "__main__":
    main()
