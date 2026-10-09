"""Command line: add/refresh the games listed in games.json (server-side).

Usage:
    python fetch_reviews.py                    # every game in games.json
    python fetch_reviews.py --app-id com.x.y   # one game by Google Play package id
"""
import argparse

import config
from core import fetcher, repo
from core.db import get_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id")
    parser.add_argument("--count", type=int)
    args = parser.parse_args()

    seed = config.load_games()
    db = get_db()
    targets = [args.app_id] if args.app_id else [g["app_id"] for g in seed["games"]]
    for app_id in targets:
        result = fetcher.collect(db, app_id, lang=seed.get("lang", "en"),
                                 country=seed.get("country", "us"),
                                 count=args.count or seed.get("reviews_per_game", 400))
        print(f"{result['game']['name']}: {result['fetched']} fetched, {result['added']} new")
        repo.log_activity(db, "cli", "refresh", app_id, n_items=result["added"])
    print("Database:", repo.stats(db))


if __name__ == "__main__":
    main()
