"""All reads and writes to the database, in one place.

The rest of the app never writes SQL: it calls these functions. That keeps
the queries easy to find, test and change.
"""
import json

import pandas as pd

import config
from core import crypto
from core.db import Database
from core.util import days_ago, new_id, now

# =============================================================================
# Users
# =============================================================================


def upsert_user(db: Database, email: str, name: str | None) -> dict:
    email = email.lower()
    db.execute(
        """INSERT INTO users (email, name, created_at, last_login, prefs)
           VALUES (:email, :name, :ts, :ts, '{}')
           ON CONFLICT (email) DO UPDATE SET last_login = excluded.last_login,
                                             name = COALESCE(excluded.name, users.name)""",
        {"email": email, "name": name, "ts": now()},
    )
    return get_user(db, email)


def get_user(db: Database, email: str) -> dict | None:
    user = db.one("SELECT * FROM users WHERE email = :email", {"email": email.lower()})
    if user:
        user["prefs"] = json.loads(user.get("prefs") or "{}")
    return user


def update_user(db: Database, email: str, **fields) -> None:
    allowed = {"display_name", "profile_link", "show_in_community", "is_banned"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if "prefs" in fields:
        sets["prefs"] = json.dumps(fields["prefs"])
    if not sets:
        return
    assignments = ", ".join(f"{k} = :{k}" for k in sets)
    db.execute(f"UPDATE users SET {assignments} WHERE email = :email",
               {**sets, "email": email.lower()})


def list_users(db: Database) -> pd.DataFrame:
    rows = db.query(
        """SELECT u.email, u.name, u.created_at, u.last_login, u.is_banned,
                  u.show_in_community,
                  CASE WHEN u.gemini_key_enc IS NULL THEN 0 ELSE 1 END AS saved_key,
                  (SELECT COUNT(*) FROM games g WHERE g.added_by = u.email) AS games_added,
                  (SELECT COUNT(*) FROM activity a WHERE a.email = u.email) AS actions
           FROM users u ORDER BY u.last_login DESC""")
    return pd.DataFrame(rows)


# --- API keys -----------------------------------------------------------------
def save_api_key(db: Database, email: str, provider: str, key: str | None) -> None:
    column = {"gemini": "gemini_key_enc", "groq": "groq_key_enc"}[provider]
    value = crypto.encrypt(key) if key else None
    db.execute(f"UPDATE users SET {column} = :v WHERE email = :email",
               {"v": value, "email": email.lower()})


def get_api_key(db: Database, email: str, provider: str) -> str | None:
    column = {"gemini": "gemini_key_enc", "groq": "groq_key_enc"}[provider]
    token = db.scalar(f"SELECT {column} FROM users WHERE email = :email",
                      {"email": email.lower()})
    return crypto.decrypt(token) if token else None


# =============================================================================
# Games
# =============================================================================


def upsert_game(db: Database, game: dict) -> None:
    db.execute(
        """INSERT INTO games (app_id, store, name, developer, genre, installs, price,
                              avg_rating, rating_count, icon_url, store_url,
                              added_by, added_at, last_fetched_at, is_hidden)
           VALUES (:app_id, :store, :name, :developer, :genre, :installs, :price,
                   :avg_rating, :rating_count, :icon_url, :store_url,
                   :added_by, :ts, :ts, 0)
           ON CONFLICT (app_id) DO UPDATE SET
               name = excluded.name, developer = excluded.developer,
               genre = excluded.genre, installs = excluded.installs,
               price = excluded.price, avg_rating = excluded.avg_rating,
               rating_count = excluded.rating_count, icon_url = excluded.icon_url,
               store_url = excluded.store_url, last_fetched_at = excluded.last_fetched_at""",
        {"store": "google_play", "added_by": None, **game, "ts": now()},
    )


def get_game(db: Database, app_id: str) -> dict | None:
    return db.one("SELECT * FROM games WHERE app_id = :a", {"a": app_id})


def list_games(db: Database, include_hidden: bool = False,
               scheme_id: str = config.DEFAULT_SCHEME_ID) -> pd.DataFrame:
    rows = db.query(
        f"""SELECT g.*,
                   (SELECT COUNT(*) FROM reviews r WHERE r.app_id = g.app_id) AS n_reviews,
                   (SELECT COUNT(*) FROM reviews r JOIN labels l ON l.review_id = r.review_id
                     WHERE r.app_id = g.app_id AND l.scheme_id = :s) AS n_labeled,
                   (SELECT MIN(r.review_date) FROM reviews r WHERE r.app_id = g.app_id) AS first_review,
                   (SELECT MAX(r.review_date) FROM reviews r WHERE r.app_id = g.app_id) AS last_review,
                   u.display_name AS added_by_name, u.profile_link AS added_by_link,
                   u.show_in_community AS added_by_public
            FROM games g LEFT JOIN users u ON u.email = g.added_by
            {'' if include_hidden else 'WHERE g.is_hidden = 0'}
            ORDER BY g.name""",
        {"s": scheme_id},
    )
    return pd.DataFrame(rows)


def set_game_hidden(db: Database, app_id: str, hidden: bool) -> None:
    db.execute("UPDATE games SET is_hidden = :h WHERE app_id = :a",
               {"h": int(hidden), "a": app_id})


def delete_game(db: Database, app_id: str) -> None:
    db.execute("""DELETE FROM labels WHERE review_id IN
                  (SELECT review_id FROM reviews WHERE app_id = :a)""", {"a": app_id})
    db.execute("DELETE FROM reviews WHERE app_id = :a", {"a": app_id})
    db.execute("DELETE FROM games WHERE app_id = :a", {"a": app_id})


# =============================================================================
# Reviews and labels
# =============================================================================


def known_review_ids(db: Database, app_id: str) -> set[str]:
    rows = db.query("SELECT review_id FROM reviews WHERE app_id = :a", {"a": app_id})
    return {r["review_id"] for r in rows}


def main_market(db: Database, app_id: str) -> tuple[str, str]:
    """(country, lang) most of this game's stored reviews come from; ('us', 'en') if none."""
    row = db.one("""SELECT country, lang, COUNT(*) AS n FROM reviews WHERE app_id = :a
                    GROUP BY country, lang ORDER BY n DESC LIMIT 1""", {"a": app_id})
    return (row["country"] or "us", row["lang"] or "en") if row else ("us", "en")


def insert_reviews(db: Database, reviews: list[dict]) -> int:
    """Insert new reviews, skip ones already stored. Returns how many were new."""
    if not reviews:
        return 0
    app_id = reviews[0]["app_id"]
    before = db.scalar("SELECT COUNT(*) FROM reviews WHERE app_id = :a", {"a": app_id})
    ts = now()
    db.executemany(
        """INSERT INTO reviews (review_id, app_id, country, lang, rating, content, version,
                                thumbs_up, review_date, fetched_at)
           VALUES (:review_id, :app_id, :country, :lang, :rating, :content, :version,
                   :thumbs_up, :review_date, :fetched_at)
           ON CONFLICT (review_id) DO NOTHING""",
        [{**r, "fetched_at": ts} for r in reviews],
    )
    after = db.scalar("SELECT COUNT(*) FROM reviews WHERE app_id = :a", {"a": app_id})
    return int(after) - int(before)


def unlabeled_reviews(db: Database, app_ids: list[str], scheme_id: str,
                      limit: int | None = None) -> list[dict]:
    if not app_ids:
        return []
    names = {f"a{i}": a for i, a in enumerate(app_ids)}
    placeholders = ", ".join(f":{k}" for k in names)
    rows = db.query(
        f"""SELECT r.review_id, r.rating, r.content, g.name AS game
            FROM reviews r JOIN games g ON g.app_id = r.app_id
            LEFT JOIN labels l ON l.review_id = r.review_id AND l.scheme_id = :scheme
            WHERE l.review_id IS NULL AND r.app_id IN ({placeholders})
            ORDER BY g.name, r.review_date DESC""",
        {**names, "scheme": scheme_id},
    )
    return rows[:limit] if limit else rows


def save_labels(db: Database, records: list[dict]) -> None:
    db.executemany(
        """INSERT INTO labels (review_id, scheme_id, sentiment, topics, feature_request,
                               model, labeled_by, labeled_at)
           VALUES (:review_id, :scheme_id, :sentiment, :topics, :feature_request,
                   :model, :labeled_by, :labeled_at)
           ON CONFLICT (review_id, scheme_id) DO UPDATE SET
               sentiment = excluded.sentiment, topics = excluded.topics,
               feature_request = excluded.feature_request, model = excluded.model,
               labeled_by = excluded.labeled_by, labeled_at = excluded.labeled_at""",
        records,
    )


def load_labeled(db: Database, app_ids: list[str],
                 scheme_id: str = config.DEFAULT_SCHEME_ID) -> pd.DataFrame:
    """One row per labeled review, with game name. Used by the dashboard and exports."""
    if not app_ids:
        return pd.DataFrame()
    names = {f"a{i}": a for i, a in enumerate(app_ids)}
    placeholders = ", ".join(f":{k}" for k in names)
    rows = db.query(
        f"""SELECT r.review_id, r.app_id, g.name AS game, r.country, r.lang, r.rating,
                   r.content, r.version, r.thumbs_up, r.review_date,
                   l.sentiment, l.topics, l.feature_request, l.model
            FROM reviews r
            JOIN games g ON g.app_id = r.app_id
            JOIN labels l ON l.review_id = r.review_id AND l.scheme_id = :scheme
            WHERE r.app_id IN ({placeholders})""",
        {**names, "scheme": scheme_id},
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["review_date"] = pd.to_datetime(df["review_date"], errors="coerce", utc=True)
    df["topics"] = df["topics"].apply(lambda t: json.loads(t) if t else ["other"])
    df["thumbs_up"] = df["thumbs_up"].fillna(0).astype(int)
    return df


# =============================================================================
# Topic schemes (custom topic lists)
# =============================================================================


def default_scheme() -> dict:
    return {"id": config.DEFAULT_SCHEME_ID, "owner_email": None, "name": "Standard topics",
            "topics": dict(config.TOPICS), "labels": dict(config.TOPIC_LABELS)}


def _scheme_from_row(row: dict) -> dict:
    topics = json.loads(row["topics"])
    labels = {k: k.replace("_", " ").capitalize() for k in topics}
    labels.update({k: v.split("(")[0].strip() for k, v in topics.items() if "(" in v})
    return {**row, "topics": topics, "labels": labels}


def get_scheme(db: Database, scheme_id: str) -> dict:
    if scheme_id == config.DEFAULT_SCHEME_ID:
        return default_scheme()
    row = db.one("SELECT * FROM topic_schemes WHERE id = :i", {"i": scheme_id})
    return _scheme_from_row(row) if row else default_scheme()


def list_schemes(db: Database, email: str | None) -> list[dict]:
    schemes = [default_scheme()]
    if email:
        rows = db.query("SELECT * FROM topic_schemes WHERE owner_email = :e ORDER BY created_at",
                        {"e": email.lower()})
        schemes += [_scheme_from_row(r) for r in rows]
    return schemes


def create_scheme(db: Database, email: str, name: str, topics: dict) -> str:
    topics = {k: v for k, v in topics.items() if k}
    topics.setdefault("other", "Anything that does not fit the topics above")
    scheme_id = new_id()
    db.execute("""INSERT INTO topic_schemes (id, owner_email, name, topics, created_at)
                  VALUES (:i, :e, :n, :t, :ts)""",
               {"i": scheme_id, "e": email.lower(), "n": name, "t": json.dumps(topics),
                "ts": now()})
    return scheme_id


def delete_scheme(db: Database, email: str, scheme_id: str) -> None:
    owned = db.scalar("SELECT COUNT(*) FROM topic_schemes WHERE id = :i AND owner_email = :e",
                      {"i": scheme_id, "e": email.lower()})
    if owned:
        db.execute("DELETE FROM labels WHERE scheme_id = :i", {"i": scheme_id})
        db.execute("DELETE FROM topic_schemes WHERE id = :i", {"i": scheme_id})


# =============================================================================
# Comparisons (saved sets of games)
# =============================================================================


def save_comparison(db: Database, email: str, name: str, app_ids: list[str],
                    scheme_id: str) -> str:
    cid = new_id()
    db.execute("""INSERT INTO comparisons (id, owner_email, name, app_ids, scheme_id, created_at)
                  VALUES (:i, :e, :n, :a, :s, :ts)""",
               {"i": cid, "e": email.lower(), "n": name, "a": json.dumps(app_ids),
                "s": scheme_id, "ts": now()})
    return cid


def list_comparisons(db: Database, email: str) -> list[dict]:
    rows = db.query("""SELECT * FROM comparisons WHERE owner_email = :e
                       ORDER BY created_at DESC""", {"e": email.lower()})
    for r in rows:
        r["app_ids"] = json.loads(r["app_ids"])
    return rows


def delete_comparison(db: Database, email: str, cid: str) -> None:
    db.execute("DELETE FROM comparisons WHERE id = :i AND owner_email = :e",
               {"i": cid, "e": email.lower()})


# =============================================================================
# Insights
# =============================================================================


def scope_key(app_ids: list[str], scheme_id: str) -> str:
    return scheme_id + "|" + ",".join(sorted(app_ids))


def save_insight(db: Database, key: str, email: str | None, model: str, content: dict) -> None:
    db.execute("""INSERT INTO insights (id, scope_key, created_by, model, content, created_at)
                  VALUES (:i, :k, :e, :m, :c, :ts)""",
               {"i": new_id(), "k": key, "e": email, "m": model,
                "c": json.dumps(content, ensure_ascii=False), "ts": now()})


def latest_insight(db: Database, key: str) -> dict | None:
    row = db.one("""SELECT * FROM insights WHERE scope_key = :k
                    ORDER BY created_at DESC LIMIT 1""", {"k": key})
    if not row:
        return None
    return {"created_at": row["created_at"], "model": row["model"],
            "created_by": row["created_by"], **json.loads(row["content"])}


# =============================================================================
# Activity log, limits, feedback, settings
# =============================================================================


def log_activity(db: Database, email: str | None, action: str, app_id: str | None = None,
                 status: str = "ok", n_calls: int = 0, n_items: int = 0,
                 details: dict | str | None = None) -> None:
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False)
    db.execute("""INSERT INTO activity (id, email, action, app_id, status, n_calls, n_items,
                                        details, created_at)
                  VALUES (:i, :e, :a, :app, :s, :c, :n, :d, :ts)""",
               {"i": new_id(), "e": email, "a": action, "app": app_id, "s": status,
                "c": n_calls, "n": n_items, "d": details, "ts": now()})


def count_activity(db: Database, email: str, actions: list[str], hours: float = 24) -> int:
    names = {f"x{i}": a for i, a in enumerate(actions)}
    placeholders = ", ".join(f":{k}" for k in names)
    return int(db.scalar(
        f"""SELECT COUNT(*) FROM activity WHERE email = :e AND created_at >= :since
            AND status != 'error' AND action IN ({placeholders})""",
        {"e": email.lower(), "since": days_ago(hours / 24), **names}) or 0)


def recent_activity(db: Database, limit: int = 200) -> pd.DataFrame:
    return pd.DataFrame(db.query(
        "SELECT * FROM activity ORDER BY created_at DESC LIMIT :n", {"n": limit}))


def add_feedback(db: Database, email: str, name: str | None, kind: str, message: str) -> None:
    db.execute("""INSERT INTO feedback (id, email, name, kind, message, status, created_at)
                  VALUES (:i, :e, :n, :k, :m, 'new', :ts)""",
               {"i": new_id(), "e": email, "n": name, "k": kind, "m": message, "ts": now()})


def list_feedback(db: Database) -> list[dict]:
    return db.query("SELECT * FROM feedback ORDER BY created_at DESC")


def set_feedback_status(db: Database, fid: str, status: str) -> None:
    db.execute("UPDATE feedback SET status = :s WHERE id = :i", {"s": status, "i": fid})


def get_setting(db: Database, key: str, default=None):
    value = db.scalar("SELECT value FROM app_settings WHERE key = :k", {"k": key})
    return json.loads(value) if value is not None else default


def set_setting(db: Database, key: str, value) -> None:
    db.execute("""INSERT INTO app_settings (key, value) VALUES (:k, :v)
                  ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
               {"k": key, "v": json.dumps(value)})


def community_members(db: Database) -> pd.DataFrame:
    """Users who chose to appear on the community page, with their contributions."""
    return pd.DataFrame(db.query(
        """SELECT COALESCE(u.display_name, u.name) AS name, u.profile_link,
                  (SELECT COUNT(*) FROM games g WHERE g.added_by = u.email) AS games_added,
                  u.created_at
           FROM users u WHERE u.show_in_community = 1 AND u.is_banned = 0
           ORDER BY games_added DESC, u.created_at"""))


def stats(db: Database) -> dict:
    return {
        "users": db.scalar("SELECT COUNT(*) FROM users"),
        "games": db.scalar("SELECT COUNT(*) FROM games WHERE is_hidden = 0"),
        "reviews": db.scalar("SELECT COUNT(*) FROM reviews"),
        "labels": db.scalar("SELECT COUNT(*) FROM labels"),
        "new_feedback": db.scalar("SELECT COUNT(*) FROM feedback WHERE status = 'new'"),
        "actions_24h": db.scalar("SELECT COUNT(*) FROM activity WHERE created_at >= :s",
                                 {"s": days_ago(1)}),
    }


def delete_user(db: Database, email: str) -> None:
    """Delete an account: saved keys, comparisons and custom topic lists.
    Games the user added stay in the shared catalog, without their name."""
    email = email.lower()
    for scheme in db.query("SELECT id FROM topic_schemes WHERE owner_email = :e", {"e": email}):
        db.execute("DELETE FROM labels WHERE scheme_id = :i", {"i": scheme["id"]})
    db.execute("DELETE FROM topic_schemes WHERE owner_email = :e", {"e": email})
    db.execute("DELETE FROM comparisons WHERE owner_email = :e", {"e": email})
    db.execute("UPDATE games SET added_by = NULL WHERE added_by = :e", {"e": email})
    db.execute("UPDATE labels SET labeled_by = NULL WHERE labeled_by = :e", {"e": email})
    db.execute("UPDATE activity SET email = 'deleted-user' WHERE email = :e", {"e": email})
    db.execute("DELETE FROM users WHERE email = :e", {"e": email})
