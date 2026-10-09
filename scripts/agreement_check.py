"""Quality check: do two LLMs agree on the labels?

Re-labels a random sample of reviews with another model WITHOUT saving and
compares the answers with the stored labels.
Usage:  python scripts/agreement_check.py --model gemini-3.5-flash [--n 100]
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core.db import get_db  # noqa: E402
from core.labeler import build_prompt, clean_result, system_prompt  # noqa: E402
from core.llm import LLMConfig, complete_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()

    db = get_db()
    rows = db.query(
        """SELECT r.review_id, r.rating, r.content, g.name AS game, l.sentiment, l.topics, l.model
           FROM reviews r JOIN games g ON g.app_id = r.app_id
           JOIN labels l ON l.review_id = r.review_id AND l.scheme_id = :s
           WHERE l.model != :m""", {"s": config.DEFAULT_SCHEME_ID, "m": args.model})
    random.seed(42)
    sample = random.sample(rows, min(args.n, len(rows)))
    llm = LLMConfig(api_key=config.GEMINI_API_KEY, model=args.model, fallbacks=[])
    same = overlap = compared = 0
    for i in range(0, len(sample), config.DEFAULT_BATCH_SIZE):
        batch = sample[i:i + config.DEFAULT_BATCH_SIZE]
        answer = complete_json(llm, system_prompt(config.TOPICS), build_prompt(batch))
        by_index = {a.get("i"): a for a in answer.get("results", []) if isinstance(a, dict)}
        for n, row in enumerate(batch, start=1):
            new = clean_result(by_index.get(n, {}), config.TOPICS)
            if new:
                compared += 1
                same += new["sentiment"] == row["sentiment"]
                overlap += bool(set(new["topics"]) & set(json.loads(row["topics"])))
    result = {"compared_reviews": compared, "check_model": args.model,
              "sentiment_agreement": round(same / max(compared, 1), 3),
              "topic_overlap": round(overlap / max(compared, 1), 3)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
