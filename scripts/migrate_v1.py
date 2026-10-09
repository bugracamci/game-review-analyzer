"""Copy the v1 data (data/reviews.db) into the v2 database (DATABASE_URL).

Safe to run more than once: rows that already exist are skipped.
Usage (from the project folder):  python scripts/migrate_v1.py
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core import repo  # noqa: E402
from core.db import get_db  # noqa: E402
from core.util import now  # noqa: E402


def main():
    if not config.LEGACY_DB_PATH.exists():
        raise SystemExit("data/reviews.db not found - nothing to migrate.")
    target = get_db()
    print(f"Target database: {target.kind}")
    old = sqlite3.connect(config.LEGACY_DB_PATH)
    old.row_factory = sqlite3.Row

    games = [dict(r) for r in old.execute("SELECT * FROM games")]
    for g in games:
        repo.upsert_game(target, {
            "app_id": g["app_id"], "store": "google_play", "name": g["name"],
            "developer": g["developer"], "genre": g.get("genre"), "installs": g.get("installs"),
            "price": g["price"], "avg_rating": g["avg_rating"], "rating_count": g["rating_count"],
            "icon_url": g["icon_url"], "store_url": g["store_url"], "added_by": None})
    print(f"games: {len(games)}")

    reviews = [dict(r) for r in old.execute("SELECT * FROM reviews")]
    by_app = {}
    for r in reviews:
        by_app.setdefault(r["app_id"], []).append({
            "review_id": r["review_id"], "app_id": r["app_id"], "country": "us", "lang": "en",
            "rating": r["rating"], "content": r["content"], "version": r["version"],
            "thumbs_up": r["thumbs_up"], "review_date": r["review_date"]})
    added = sum(repo.insert_reviews(target, rows) for rows in by_app.values())
    print(f"reviews: {len(reviews)} ({added} new)")

    labels = [dict(r) for r in old.execute("SELECT * FROM classifications")]
    repo.save_labels(target, [{
        "review_id": c["review_id"], "scheme_id": config.DEFAULT_SCHEME_ID,
        "sentiment": c["sentiment"], "topics": c["topics"],
        "feature_request": c["feature_request"], "model": c["model"],
        "labeled_by": None, "labeled_at": c["classified_at"] or now()} for c in labels])
    print(f"labels: {len(labels)}")

    row = old.execute("SELECT model, content FROM insights ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        ids = [g["app_id"] for g in games]
        key = repo.scope_key(ids, config.DEFAULT_SCHEME_ID)
        if not repo.latest_insight(target, key):
            repo.save_insight(target, key, None, row["model"], json.loads(row["content"]))
        print("insights: 1")

    print("\nCheck:", repo.stats(target))


if __name__ == "__main__":
    main()
