"""Step 1 - Download Google Play reviews for every game in games.json.

Why Google Play? Apple's public review RSS feed still answers but returns
zero reviews for every app (checked Oct 2026), so it can no longer be used.
The free `google-play-scraper` package reads Google Play's public pages.

Usage:
    python fetch_reviews.py                # all games in games.json
    python fetch_reviews.py --game Brotato # only one game
    python fetch_reviews.py --search "Magic Survival"   # find a game's app id

To add a game: add {"name", "developer", "app_id"} to games.json (app_id may be
null - it is then searched by name, accepting only the given developer).
To remove a game: delete it from games.json and run this script again.
"""
import argparse
import time
from datetime import datetime, timezone

from google_play_scraper import Sort, app as gp_app, reviews as gp_reviews, search as gp_search

from config import load_games, save_games
from db import connect


def find_app_id(term: str, lang: str, country: str, developer: str = "") -> str | None:
    """Search Google Play by name. Only accepts a result from the expected developer,
    because search results are full of copycat games with similar names."""
    try:
        results = gp_search(term, lang=lang, country=country, n_hits=10)
    except Exception as e:
        print(f"  search failed: {e}")
        return None
    for r in results:
        print(f"    candidate: {r.get('title')} | {r.get('developer')} | {r.get('appId')}")
    matches = [r for r in results if r.get("appId")
               and developer.lower() in str(r.get("developer", "")).lower()]
    return matches[0]["appId"] if matches else None


def prune_removed_games(conn, keep_ids: set[str]) -> None:
    """Delete data for games that are no longer listed in games.json."""
    old = [row[0] for row in conn.execute("SELECT app_id FROM games")]
    for app_id in old:
        if app_id in keep_ids:
            continue
        conn.execute("""DELETE FROM classifications WHERE review_id IN
                        (SELECT review_id FROM reviews WHERE app_id = ?)""", (app_id,))
        n = conn.execute("DELETE FROM reviews WHERE app_id = ?", (app_id,)).rowcount
        conn.execute("DELETE FROM games WHERE app_id = ?", (app_id,))
        print(f"Removed {app_id} ({n} reviews) - no longer in games.json")
    conn.commit()


def fetch_reviews(app_id: str, lang: str, country: str, count: int) -> list[dict]:
    """Download the newest `count` reviews, 200 at a time."""
    collected, token = [], None
    while len(collected) < count:
        batch, token = gp_reviews(app_id, lang=lang, country=country, sort=Sort.NEWEST,
                                  count=min(200, count - len(collected)),
                                  continuation_token=token)
        if not batch:
            break
        collected.extend(batch)
        print(f"    {len(collected)} reviews so far")
        if not token or not token.token:
            break
        time.sleep(1)  # be polite
    return [
        {
            "review_id": r["reviewId"],
            "app_id": app_id,
            "rating": r["score"],
            "content": (r.get("content") or "").strip(),
            "version": r.get("reviewCreatedVersion") or r.get("appVersion"),
            "thumbs_up": r.get("thumbsUpCount", 0),
            "review_date": r["at"].isoformat() if r.get("at") else None,
        }
        for r in collected
        if (r.get("content") or "").strip()  # skip empty reviews
    ]


def save(conn, game: dict, reviews: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO games (app_id, name, store, genre, installs, developer, price,
                              avg_rating, rating_count, icon_url, store_url, fetched_at)
           VALUES (:app_id, :name, :store, :genre, :installs, :developer, :price,
                   :avg_rating, :rating_count, :icon_url, :store_url, :fetched_at)
           ON CONFLICT(app_id) DO UPDATE SET
               name=excluded.name, genre=excluded.genre, installs=excluded.installs,
               developer=excluded.developer, price=excluded.price,
               avg_rating=excluded.avg_rating, rating_count=excluded.rating_count,
               icon_url=excluded.icon_url, store_url=excluded.store_url,
               fetched_at=excluded.fetched_at""",
        {**game, "fetched_at": now},
    )
    before = conn.total_changes
    conn.executemany(
        """INSERT OR IGNORE INTO reviews (review_id, app_id, rating, content, version,
                                         thumbs_up, review_date)
           VALUES (:review_id, :app_id, :rating, :content, :version, :thumbs_up, :review_date)""",
        reviews,
    )
    conn.commit()
    return conn.total_changes - before


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", help="only fetch this game (name as in games.json)")
    parser.add_argument("--search", help="search Google Play and print candidates")
    args = parser.parse_args()

    config = load_games()
    lang, country = config.get("lang", "en"), config.get("country", "us")

    if args.search:
        find_app_id(args.search, lang, country)
        return

    conn = connect()
    if not args.game:
        prune_removed_games(conn, {g["app_id"] for g in config["games"] if g.get("app_id")})
    changed_config = False
    for game in config["games"]:
        if args.game and game["name"].lower() != args.game.lower():
            continue
        print(f"\n== {game['name']} ==")
        app_id = game.get("app_id")
        if not app_id:
            app_id = find_app_id(game["name"], lang, country, game.get("developer", ""))
            if not app_id:
                print("  No result from the expected developer - add app_id to games.json by hand.")
                continue
            game["app_id"] = app_id  # remember it, so future runs are exact
            changed_config = True

        try:
            info = gp_app(app_id, lang=lang, country=country)
        except Exception as e:
            print(f"  Could not load app page for {app_id}: {e}")
            continue
        print(f"  Using: {info['title']} by {info.get('developer')} ({app_id})")
        expected = game.get("developer", "")
        if expected.lower() not in str(info.get("developer", "")).lower():
            print(f"  WARNING: expected developer '{expected}' - skipping this game. "
                  f"Check its app_id in games.json.")
            continue

        details = {
            "app_id": app_id,
            "name": game["name"],
            "store": "google_play",
            "genre": info.get("genre"),
            "installs": info.get("installs"),
            "developer": info.get("developer"),
            "price": info.get("price"),
            "avg_rating": info.get("score"),
            "rating_count": info.get("ratings"),
            "icon_url": info.get("icon"),
            "store_url": info.get("url"),
        }
        reviews = fetch_reviews(app_id, lang, country, config.get("reviews_per_game", 400))
        added = save(conn, details, reviews)
        dates = sorted(r["review_date"] for r in reviews if r["review_date"])
        span = f"{dates[0][:10]} -> {dates[-1][:10]}" if dates else "no dates"
        print(f"  {len(reviews)} reviews ({span}), {added} new saved.")

    if changed_config:
        save_games(config)
        print("\nSaved the found app ids into games.json.")

    total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    print(f"\nTotal reviews in database: {total}")


if __name__ == "__main__":
    main()
