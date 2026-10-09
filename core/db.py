"""A tiny database layer that works with both SQLite (local) and Postgres (Supabase).

Why not an ORM? The app needs ~40 simple queries. A 100-line adapter keeps the
SQL readable, has one dependency (psycopg2) and runs the same SQL on both
databases. Queries use named parameters like :email in both cases.
"""
import re
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        email            TEXT PRIMARY KEY,
        name             TEXT,
        created_at       TEXT,
        last_login       TEXT,
        is_banned        INTEGER DEFAULT 0,
        gemini_key_enc   TEXT,
        groq_key_enc     TEXT,
        prefs            TEXT,      -- JSON: model, batch size, reviews per game, market
        display_name     TEXT,
        profile_link     TEXT,
        show_in_community INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS games (
        app_id        TEXT PRIMARY KEY,
        store         TEXT,
        name          TEXT NOT NULL,
        developer     TEXT,
        genre         TEXT,
        installs      TEXT,
        price         REAL,
        avg_rating    REAL,
        rating_count  INTEGER,
        icon_url      TEXT,
        store_url     TEXT,
        added_by      TEXT,
        added_at      TEXT,
        last_fetched_at TEXT,
        is_hidden     INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS reviews (
        review_id   TEXT PRIMARY KEY,
        app_id      TEXT NOT NULL,
        country     TEXT,
        lang        TEXT,
        rating      INTEGER,
        content     TEXT,
        version     TEXT,
        thumbs_up   INTEGER,
        review_date TEXT,
        fetched_at  TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_reviews_app ON reviews (app_id)",
    """CREATE TABLE IF NOT EXISTS topic_schemes (
        id          TEXT PRIMARY KEY,
        owner_email TEXT,
        name        TEXT,
        topics      TEXT,      -- JSON {key: description}
        created_at  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS labels (
        review_id       TEXT NOT NULL,
        scheme_id       TEXT NOT NULL,
        sentiment       TEXT,
        topics          TEXT,  -- JSON list of topic keys
        feature_request TEXT,
        model           TEXT,
        labeled_by      TEXT,
        labeled_at      TEXT,
        PRIMARY KEY (review_id, scheme_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_labels_scheme ON labels (scheme_id)",
    """CREATE TABLE IF NOT EXISTS comparisons (
        id          TEXT PRIMARY KEY,
        owner_email TEXT,
        name        TEXT,
        app_ids     TEXT,      -- JSON list
        scheme_id   TEXT,
        created_at  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS insights (
        id          TEXT PRIMARY KEY,
        scope_key   TEXT,      -- scheme + sorted app ids
        created_by  TEXT,
        model       TEXT,
        content     TEXT,      -- JSON written by the LLM
        created_at  TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_insights_scope ON insights (scope_key)",
    """CREATE TABLE IF NOT EXISTS activity (
        id          TEXT PRIMARY KEY,
        email       TEXT,
        action      TEXT,      -- add_game, refresh, label, insights, export, ...
        app_id      TEXT,
        status      TEXT,      -- ok, error, stopped
        n_calls     INTEGER,
        n_items     INTEGER,
        details     TEXT,
        created_at  TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_activity_email ON activity (email)",
    """CREATE TABLE IF NOT EXISTS feedback (
        id          TEXT PRIMARY KEY,
        email       TEXT,
        name        TEXT,
        kind        TEXT,      -- hello, game_request, bug, idea
        message     TEXT,
        status      TEXT,      -- new, read, done
        created_at  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS app_settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""",
]

_PARAM = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


class Database:
    def __init__(self, url: str):
        self.url = url
        self.kind = "sqlite" if url.startswith("sqlite") else "postgres"
        self._conn = None
        self._lock = threading.RLock()

    # --- connection -------------------------------------------------------------
    def _connect(self):
        if self.kind == "sqlite":
            path = self.url.split("sqlite:///", 1)[1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        import psycopg2  # only needed for Postgres
        conn = psycopg2.connect(self.url, connect_timeout=15)
        conn.autocommit = True
        return conn

    def _sql(self, sql: str) -> str:
        if self.kind == "sqlite":
            return sql
        return _PARAM.sub(r"%(\1)s", sql.replace("%", "%%"))

    def _run(self, fn):
        """Run fn(conn); on a dropped Postgres connection reconnect and retry once."""
        with self._lock:
            for attempt in range(3):
                try:
                    if self._conn is None:
                        self._conn = self._connect()
                    return fn(self._conn)
                except Exception as e:  # noqa: BLE001
                    if self.kind == "postgres" and _is_connection_error(e) and attempt < 2:
                        self._conn = None
                        time.sleep(1 + attempt)
                        continue
                    raise

    # --- public API --------------------------------------------------------------
    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        def fn(conn):
            cur = conn.cursor()
            cur.execute(self._sql(sql), params or {})
            if cur.description is None:
                return []
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            cur.close()
            return rows
        return self._run(fn)

    def one(self, sql: str, params: dict | None = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: dict | None = None):
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def execute(self, sql: str, params: dict | None = None) -> int:
        def fn(conn):
            cur = conn.cursor()
            cur.execute(self._sql(sql), params or {})
            n = cur.rowcount
            cur.close()
            if self.kind == "sqlite":
                conn.commit()
            return n
        return self._run(fn)

    def executemany(self, sql: str, rows: list[dict]) -> None:
        if not rows:
            return

        def fn(conn):
            cur = conn.cursor()
            if self.kind == "sqlite":
                cur.executemany(sql, rows)
                conn.commit()
            else:
                from psycopg2.extras import execute_batch
                execute_batch(cur, self._sql(sql), rows, page_size=200)
            cur.close()
        self._run(fn)

    def init_schema(self) -> None:
        for statement in SCHEMA:
            self.execute(statement)


def _is_connection_error(e: Exception) -> bool:
    name = type(e).__name__
    return name in ("OperationalError", "InterfaceError") or "closed" in str(e).lower()


_instances: dict[str, Database] = {}


def get_db(url: str | None = None) -> Database:
    """One shared Database per URL, with the schema created on first use."""
    import config
    url = url or config.DATABASE_URL
    if url not in _instances:
        db = Database(url)
        db.init_schema()
        _instances[url] = db
    return _instances[url]
