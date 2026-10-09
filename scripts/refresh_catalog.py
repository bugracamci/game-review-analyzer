"""Weekly job (GitHub Actions): fetch new reviews for every catalog game and label them.

Uses the server's own Gemini key with a call budget, so it stays inside the
free tier. It also keeps the free Supabase database active.
Usage:  python scripts/refresh_catalog.py [--max-calls 18] [--per-game 200]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core import fetcher, labeler, repo  # noqa: E402
from core.db import get_db  # noqa: E402
from core.llm import LLMConfig  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=18)
    parser.add_argument("--per-game", type=int, default=200)
    args = parser.parse_args()

    db = get_db()
    games = repo.list_games(db)
    print(f"{len(games)} games in the catalog")
    for _, g in games.iterrows():
        try:
            r = fetcher.collect(db, g["app_id"], count=args.per_game)
            print(f"  {g['name']}: {r['added']} new reviews")
            repo.log_activity(db, "weekly-job", "refresh", g["app_id"], n_items=r["added"])
        except Exception as e:  # noqa: BLE001 - one broken game must not stop the job
            print(f"  {g['name']}: failed ({e})")
            repo.log_activity(db, "weekly-job", "refresh", g["app_id"], status="error",
                              details=str(e)[:300])

    if not config.GEMINI_API_KEY:
        print("No GEMINI_API_KEY - skipping labeling.")
        return
    summary = labeler.label(db, list(games["app_id"]), LLMConfig(api_key=config.GEMINI_API_KEY),
                            user_email="weekly-job", max_calls=args.max_calls)
    print("Labeling:", summary)
    repo.log_activity(db, "weekly-job", "label", n_calls=summary["calls"],
                      n_items=summary["labeled"],
                      status="stopped" if summary["stopped"] else "ok")


if __name__ == "__main__":
    main()
