"""SQLite helpers. One file (data/reviews.db) holds everything:
games, raw reviews, LLM classifications and generated insights."""
import sqlite3

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    app_id        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    store         TEXT,
    genre         TEXT,
    installs      TEXT,
    developer     TEXT,
    price         REAL,
    avg_rating    REAL,
    rating_count  INTEGER,
    icon_url      TEXT,
    store_url     TEXT,
    fetched_at    TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id  TEXT PRIMARY KEY,
    app_id     TEXT NOT NULL REFERENCES games(app_id),
    rating     INTEGER,
    content    TEXT,
    version    TEXT,
    thumbs_up  INTEGER,
    review_date TEXT
);

CREATE TABLE IF NOT EXISTS classifications (
    review_id        TEXT PRIMARY KEY REFERENCES reviews(review_id),
    sentiment        TEXT,
    topics           TEXT,   -- JSON list, e.g. ["monetization_ads", "difficulty_balance"]
    feature_request  TEXT,   -- short summary or NULL
    model            TEXT,
    classified_at    TEXT
);

CREATE TABLE IF NOT EXISTS insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT,
    model       TEXT,
    content     TEXT     -- JSON produced by the LLM
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
