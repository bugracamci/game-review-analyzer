"""Collect games and reviews from Google Play.

Why Google Play? Apple's public review RSS feed answers but returns zero
reviews for every app (tested Oct 2026). The open-source google-play-scraper
package reads Google Play's public pages, with no key needed.
"""
import re
import time
from urllib.parse import parse_qs, urlparse

from core import repo
from core.db import Database
from core.util import now

PACKAGE_RE = re.compile(r"^[A-Za-z][\w]*(\.[A-Za-z_][\w]*)+$")


def parse_app_id(text: str) -> str | None:
    """Accept a Google Play link or a package name like com.example.game."""
    text = (text or "").strip()
    if "play.google.com" in text:
        ids = parse_qs(urlparse(text).query).get("id")
        text = ids[0] if ids else ""
    return text if PACKAGE_RE.match(text) else None


def search_games(term: str, lang: str = "en", country: str = "us", n: int = 8) -> list[dict]:
    from google_play_scraper import search
    results = search(term, lang=lang, country=country, n_hits=n)
    return [{"app_id": r.get("appId"), "name": r.get("title"), "developer": r.get("developer"),
             "icon_url": r.get("icon"), "genre": r.get("genre"), "score": r.get("score"),
             "installs": r.get("installs")}
            for r in results if r.get("appId")]


def lookup_game(app_id: str, lang: str = "en", country: str = "us") -> dict:
    """Store details for one game. Raises ValueError if it doesn't exist."""
    from google_play_scraper import app as gp_app
    try:
        info = gp_app(app_id, lang=lang, country=country)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Could not find '{app_id}' on Google Play.") from e
    return {
        "app_id": app_id,
        "store": "google_play",
        "name": info.get("title") or app_id,
        "developer": info.get("developer"),
        "genre": info.get("genre"),
        "installs": info.get("installs"),
        "price": info.get("price"),
        "avg_rating": info.get("score"),
        "rating_count": info.get("ratings"),
        "icon_url": info.get("icon"),
        "store_url": info.get("url"),
    }


def fetch_new_reviews(app_id: str, lang: str, country: str, count: int,
                      known_ids: set[str] | None = None, progress=None) -> list[dict]:
    """Newest reviews, 200 per page, stopping early once we reach reviews we already have."""
    from google_play_scraper import Sort, reviews as gp_reviews
    known_ids = known_ids or set()
    collected, token = [], None
    while len(collected) < count:
        batch, token = gp_reviews(app_id, lang=lang, country=country, sort=Sort.NEWEST,
                                  count=min(200, count - len(collected)),
                                  continuation_token=token)
        if not batch:
            break
        fresh = [r for r in batch if r["reviewId"] not in known_ids]
        collected.extend(fresh)
        if progress:
            progress(len(collected), count)
        if len(fresh) < len(batch) or not token or not getattr(token, "token", None):
            break  # reached reviews we already have, or no more pages
        time.sleep(1)
    return [
        {
            "review_id": r["reviewId"],
            "app_id": app_id,
            "country": country,
            "lang": lang,
            "rating": r["score"],
            "content": (r.get("content") or "").strip(),
            "version": r.get("reviewCreatedVersion") or r.get("appVersion"),
            "thumbs_up": r.get("thumbsUpCount") or 0,
            "review_date": r["at"].isoformat() if r.get("at") else None,
        }
        for r in collected if (r.get("content") or "").strip()
    ]


def collect(db: Database, app_id: str, lang: str = "en", country: str = "us",
            count: int = 400, added_by: str | None = None, progress=None) -> dict:
    """Add a game to the catalog (or refresh it) and store its newest reviews."""
    existing = repo.get_game(db, app_id)
    game = lookup_game(app_id, lang, country)
    game["added_by"] = existing["added_by"] if existing else added_by
    repo.upsert_game(db, game)
    reviews = fetch_new_reviews(app_id, lang, country, count,
                                known_ids=repo.known_review_ids(db, app_id), progress=progress)
    added = repo.insert_reviews(db, reviews)
    db.execute("UPDATE games SET last_fetched_at = :ts WHERE app_id = :a",
               {"ts": now(), "a": app_id})
    return {"game": game, "is_new": existing is None, "fetched": len(reviews), "added": added}
