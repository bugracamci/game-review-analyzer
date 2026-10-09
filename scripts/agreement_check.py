"""Quality check: do two LLMs agree on the labels?

Re-labels a random sample of reviews (default 100) with another model WITHOUT
saving, and compares the answers with the saved labels. Run from the project
folder:  python scripts/agreement_check.py --model gemini-3.1-flash-lite
Results are printed and saved to logs/agreement.json.
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from classify_reviews import SYSTEM_PROMPT, build_prompt, clean_result  # noqa: E402
from db import connect  # noqa: E402
from llm_client import complete_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="model to compare against")
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()

    config.GEMINI_MODEL = args.model
    config.GEMINI_FALLBACK_MODELS.clear()  # compare exactly this model

    conn = connect()
    rows = conn.execute(
        """SELECT r.review_id, r.rating, r.content, g.name AS game,
                  c.sentiment, c.topics, c.model
           FROM reviews r JOIN games g ON g.app_id = r.app_id
           JOIN classifications c ON c.review_id = r.review_id
           WHERE c.model != ?""", (args.model,)).fetchall()
    random.seed(42)
    sample = random.sample(rows, min(args.n, len(rows)))

    same_sentiment = topic_overlap = compared = 0
    for i in range(0, len(sample), config.BATCH_SIZE):
        batch = sample[i:i + config.BATCH_SIZE]
        answer = complete_json(SYSTEM_PROMPT, build_prompt(batch))
        by_index = {a.get("i"): a for a in answer.get("results", []) if isinstance(a, dict)}
        for n, row in enumerate(batch, start=1):
            new = clean_result(by_index.get(n, {}))
            if not new:
                continue
            compared += 1
            same_sentiment += new["sentiment"] == row["sentiment"]
            topic_overlap += bool(set(new["topics"]) & set(json.loads(row["topics"])))
        print(f"  compared {compared} reviews...")

    result = {
        "compared_reviews": compared,
        "original_models": sorted({r["model"] for r in sample}),
        "check_model": args.model,
        "sentiment_agreement": round(same_sentiment / compared, 3),
        "topic_overlap": round(topic_overlap / compared, 3),
    }
    print(json.dumps(result, indent=2))
    Path("logs").mkdir(exist_ok=True)
    Path("logs/agreement.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
