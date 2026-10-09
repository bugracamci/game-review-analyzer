"""Command line: label every unlabeled review with the server's Gemini key.

Usage:  python classify_reviews.py [--max-calls 20]
"""
import argparse

import config
from core import labeler, repo
from core.db import get_db
from core.llm import LLMConfig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int)
    args = parser.parse_args()
    if not config.GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY is missing in .env")

    db = get_db()
    app_ids = list(repo.list_games(db, include_hidden=True)["app_id"])
    llm = LLMConfig(api_key=config.GEMINI_API_KEY)
    summary = labeler.label(
        db, app_ids, llm, max_calls=args.max_calls,
        progress=lambda b, n, done: print(f"  batch {b}/{n}: {done} labeled so far"))
    print(summary)
    repo.log_activity(db, "cli", "label", n_calls=summary["calls"], n_items=summary["labeled"],
                      status="stopped" if summary["stopped"] else "ok")


if __name__ == "__main__":
    main()
