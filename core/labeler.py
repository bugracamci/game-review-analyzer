"""Label reviews with an LLM: sentiment, 1-3 topics and an optional feature request.

Reviews go to the model in batches (default 25) and come back as JSON. Every
batch is saved right away, so a stopped run (quota, closed tab, Ctrl+C)
continues where it left off next time.
"""
import json

import config
from core import repo
from core.db import Database
from core.llm import BadKey, LLMConfig, LLMError, QuotaExhausted, complete_json
from core.util import now

MAX_REVIEW_CHARS = 700


def system_prompt(topics: dict) -> str:
    topic_lines = "\n".join(f'    "{k}": {v}' for k, v in topics.items())
    return f"""You are a games user-research analyst. You label mobile game reviews
so small game teams can compare competing games.

For each review return:
- "sentiment": one of {config.SENTIMENTS}. Judge the TEXT, not the star rating.
- "topics": 1 to 3 topic keys from this list (use "other" only if nothing fits):
{topic_lines}
- "feature_request": if the player asks for a new feature, change or content,
  summarize it in max 12 English words. Otherwise null.

Reviews may be in any language; always answer in English.
Answer ONLY with JSON in this exact shape:
{{"results": [{{"i": 1, "sentiment": "negative", "topics": ["{next(iter(topics))}"], "feature_request": null}}]}}
Return exactly one result per review, using the same "i" numbers."""


def build_prompt(batch: list[dict]) -> str:
    items = [{"i": n, "game": r["game"], "stars": r["rating"],
              "text": (r["content"] or "")[:MAX_REVIEW_CHARS]}
             for n, r in enumerate(batch, start=1)]
    return "Label these reviews:\n" + json.dumps(items, ensure_ascii=False)


def clean_result(item: dict, topics: dict) -> dict | None:
    """Validate one model answer; fix small issues, reject broken ones."""
    sentiment = str(item.get("sentiment", "")).lower().strip()
    if sentiment not in config.SENTIMENTS:
        return None
    chosen = [t for t in (item.get("topics") or []) if t in topics][:3]
    if not chosen:
        chosen = ["other"] if "other" in topics else [next(iter(topics))]
    request = item.get("feature_request")
    if not isinstance(request, str) or request.strip().lower() in ("", "null", "none", "n/a", "nan"):
        request = None
    return {"sentiment": sentiment, "topics": chosen, "feature_request": request}


def label(db: Database, app_ids: list[str], llm: LLMConfig, scheme_id: str = config.DEFAULT_SCHEME_ID,
          user_email: str | None = None, batch_size: int = config.DEFAULT_BATCH_SIZE,
          max_calls: int | None = None, progress=None) -> dict:
    """Label every not-yet-labeled review of these games. Returns a summary dict."""
    scheme = repo.get_scheme(db, scheme_id)
    topics = scheme["topics"]
    rows = repo.unlabeled_reviews(db, app_ids, scheme["id"])
    batches = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]
    if max_calls is not None:
        batches = batches[:max_calls]
    summary = {"to_label": len(rows), "labeled": 0, "batches": len(batches),
               "stopped": None, "models": set()}
    prompt_system = system_prompt(topics)

    for b, batch in enumerate(batches, start=1):
        try:
            answer = complete_json(llm, prompt_system, build_prompt(batch))
        except (QuotaExhausted, BadKey) as e:
            summary["stopped"] = str(e)
            break
        except LLMError as e:
            llm.log(f"batch {b} failed ({e}); it will be retried next run")
            continue
        by_index = {a.get("i"): a for a in answer.get("results", []) if isinstance(a, dict)}
        ts = now()
        records = []
        for n, row in enumerate(batch, start=1):
            result = clean_result(by_index.get(n, {}), topics)
            if result:
                records.append({"review_id": row["review_id"], "scheme_id": scheme["id"],
                                "sentiment": result["sentiment"],
                                "topics": json.dumps(result["topics"]),
                                "feature_request": result["feature_request"],
                                "model": llm.model, "labeled_by": user_email,
                                "labeled_at": ts})
        repo.save_labels(db, records)
        summary["labeled"] += len(records)
        if progress:
            progress(b, len(batches), summary["labeled"])

    summary["models"] = sorted(llm.models_used)
    summary["calls"] = llm.calls
    return summary
