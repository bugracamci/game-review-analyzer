"""Collect games and reviews from Google Play.

Why Google Play? Apple's public review RSS feed answers but returns zero
reviews for every app (tested Oct 2026). The open-source google-play-scraper
package reads Google Play's public pages, with no key needed.
"""
import re
import time
from datetime import date
from urllib.parse import parse_qs, urlparse

import config
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


def version_key(v) -> tuple:
    """Sort '1.10.2' after '1.9.0' (natural version order)."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-_ ]", str(v or "")))


def _row(r: dict, app_id: str, lang: str, country: str) -> dict:
    return {
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


def fetch_reviews(app_id: str, lang: str, country: str, count: int,
                  known_ids: set[str] | None = None, mode: str = "new",
                  start: date | None = None, end: date | None = None,
                  version: str | None = None, max_pages: int = config.FETCH_MAX_PAGES,
                  on_page=None, progress=None) -> dict:
    """Read Google Play reviews newest-first and keep up to `count` we don't have yet.

    mode="new":   stop at the first review we already have (a refresh).
    mode="older": read past the stored reviews to reach older ones ("load more").
    mode="range": keep only reviews between `start` and `end` (dates) and/or of one app
                  `version`; stop once we're past the start date or past the version.
    Google Play only lists reviews newest-first, so reaching old dates means reading every
    newer review on the way (one request per 200 reviews) - capped by `max_pages`.
    `on_page(rows)` is called with each page's kept reviews, so progress is saved as we go.
    """
    from google_play_scraper import Sort, reviews as gp_reviews
    known_ids = known_ids or set()
    target = version_key(version) if version else None
    kept, pages, token, oldest, seen_target, stop = 0, 0, None, None, False, None
    while kept < count and pages < max_pages:
        batch, token = gp_reviews(app_id, lang=lang, country=country, sort=Sort.NEWEST,
                                  count=200, continuation_token=token)
        pages += 1
        if not batch:
            stop = "end of reviews"
            break
        rows, older_page = [], True
        for r in batch:
            at = r.get("at")
            day = at.date() if at else None
            oldest = day or oldest
            is_target = True
            if target:  # track where we are relative to the wanted version
                vk = version_key(r.get("reviewCreatedVersion") or r.get("appVersion"))
                is_target = vk == target
                seen_target = seen_target or is_target
                older_page = older_page and vk < target
            if r["reviewId"] in known_ids:
                if mode == "new":
                    stop = "reached stored reviews"
                    break
                continue
            if mode == "range":
                if end and day and day > end:
                    continue
                if start and day and day < start:
                    stop = "passed the start date"
                    break
                if not is_target:
                    continue
            if (r.get("content") or "").strip():
                rows.append(_row(r, app_id, lang, country))
                if kept + len(rows) >= count:
                    break
        kept += len(rows)
        if rows and on_page:
            on_page(rows)
        if progress:
            progress(kept, count, oldest, pages)
        if stop:
            break
        if target and older_page:  # a whole page of older versions: we're past it
            stop = "passed the version" if seen_target else "version not found"
            break
        if not token or not getattr(token, "token", None):
            stop = "end of reviews"
            break
        time.sleep(0.6)
    if not stop:
        stop = "got enough" if kept >= count else "read limit reached"
    return {"kept": kept, "pages": pages, "oldest": oldest, "stop": stop}


def collect(db: Database, app_id: str, lang: str = "en", country: str = "us",
            count: int = 400, added_by: str | None = None, progress=None,
            mode: str = "new", start: date | None = None, end: date | None = None,
            version: str | None = None) -> dict:
    """Add a game to the catalog (or update it) and store reviews we don't have yet."""
    existing = repo.get_game(db, app_id)
    game = lookup_game(app_id, lang, country)
    game["added_by"] = existing["added_by"] if existing else added_by
    if existing:  # Google Play sometimes omits a field: keep what we had instead of blanking it
        for k, v in game.items():
            if v is None and existing.get(k) is not None:
                game[k] = existing[k]
    repo.upsert_game(db, game)
    added = 0

    def save(rows):
        nonlocal added
        added += repo.insert_reviews(db, rows)

    info = fetch_reviews(app_id, lang, country, count, known_ids=repo.known_review_ids(db, app_id),
                         mode=mode, start=start, end=end, version=version,
                         on_page=save, progress=progress)
    db.execute("UPDATE games SET last_fetched_at = :ts WHERE app_id = :a",
               {"ts": now(), "a": app_id})
    return {"game": game, "is_new": existing is None, "fetched": info["kept"], "added": added,
            **info}
