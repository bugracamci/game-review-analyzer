"""Turn labeled reviews into downloadable files: CSV, Excel (3 sheets) or JSON."""
import io
import json

import pandas as pd


def tidy(df: pd.DataFrame, labels: dict) -> pd.DataFrame:
    """One clean row per review, ready for spreadsheets."""
    if df.empty:
        return df
    out = df.copy()
    out["topics"] = out["topics"].apply(lambda ts: ", ".join(labels.get(t, t) for t in ts))
    out["review_date"] = out["review_date"].dt.strftime("%Y-%m-%d")
    cols = ["game", "app_id", "review_date", "rating", "sentiment", "topics",
            "feature_request", "content", "version", "thumbs_up", "country", "lang",
            "model", "review_id"]
    return out[[c for c in cols if c in out.columns]]


def summary_table(df: pd.DataFrame, labels: dict) -> pd.DataFrame:
    rows = []
    for game, g in df.groupby("game"):
        row = {"game": game, "reviews": len(g), "avg_stars": round(g["rating"].mean(), 2)}
        for s in ("positive", "neutral", "negative"):
            row[f"{s}_share"] = round((g["sentiment"] == s).mean(), 3)
        topics = g.explode("topics")["topics"].value_counts() / len(g)
        for key, label in labels.items():
            row[f"topic: {label}"] = round(float(topics.get(key, 0)), 3)
        rows.append(row)
    return pd.DataFrame(rows)


def to_csv(df: pd.DataFrame, labels: dict) -> bytes:
    return tidy(df, labels).to_csv(index=False).encode("utf-8-sig")  # BOM: opens cleanly in Excel


def to_json(df: pd.DataFrame, labels: dict) -> bytes:
    records = tidy(df, labels).to_dict(orient="records")
    return json.dumps(records, ensure_ascii=False, indent=1).encode("utf-8")


def to_excel(df: pd.DataFrame, labels: dict) -> bytes:
    buffer = io.BytesIO()
    reviews = tidy(df, labels)
    requests = reviews[reviews["feature_request"].notna()][
        ["game", "rating", "feature_request", "thumbs_up", "review_date"]]
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_table(df, labels).to_excel(writer, sheet_name="Summary", index=False)
        reviews.to_excel(writer, sheet_name="Reviews", index=False)
        requests.to_excel(writer, sheet_name="Feature requests", index=False)
    return buffer.getvalue()
