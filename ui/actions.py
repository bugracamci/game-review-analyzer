"""Long-running actions (collect, label, insights) with live progress in the page.

Each one checks the user's daily limit, uses the user's own API key, logs the
run to the activity table and refreshes the cached data when done.
"""
import streamlit as st

from core import fetcher, insights, labeler, limits, repo
from core.llm import BadKey, LLMError, QuotaExhausted
from ui.auth import is_admin
from ui.data import db, refresh_caches, user_llm, user_prefs

NO_KEY_MSG = ("Add your free Gemini API key in **Settings** first "
              "([get one in 1 minute](https://aistudio.google.com/apikey)).")


def _limit_ok(user: dict, limit_name: str) -> bool:
    ok, remaining = limits.check(db(), user["email"], limit_name, is_admin(user))
    if not ok:
        st.warning("You've reached today's limit for this action. It resets within 24 hours.")
    return ok


def run_labeling(user: dict, app_ids: list[str], scheme_id: str) -> dict | None:
    if not _limit_ok(user, "label_runs_per_day"):
        return None
    with st.status("Labeling reviews with AI…", expanded=True) as status:
        llm = user_llm(user, log=status.write)
        if not llm:
            status.update(label="No API key", state="error")
            st.markdown(NO_KEY_MSG)
            return None
        bar = st.progress(0.0, text="Starting…")
        summary = labeler.label(
            db(), app_ids, llm, scheme_id=scheme_id, user_email=user["email"],
            batch_size=int(user_prefs(user)["batch_size"]),
            progress=lambda b, n, done: bar.progress(b / n, text=f"Batch {b}/{n} · {done} labeled"))
        repo.log_activity(db(), user["email"], "label", ",".join(app_ids)[:200],
                          status="stopped" if summary["stopped"] else "ok",
                          n_calls=summary["calls"], n_items=summary["labeled"],
                          details={"scheme": scheme_id, "models": summary["models"]})
        refresh_caches()
        if summary["stopped"]:
            status.update(label=f"Paused after {summary['labeled']} reviews", state="error")
            st.warning(summary["stopped"])
        else:
            status.update(label=f"Done: {summary['labeled']} reviews labeled", state="complete")
    return summary


def run_collect(user: dict, app_id: str, country: str, lang: str, count: int,
                is_new: bool, mode: str = "new", start=None, end=None,
                version: str | None = None) -> dict | None:
    """Download reviews. mode: new / older / range (see core.fetcher.fetch_reviews)."""
    if is_new and not _limit_ok(user, "new_games_per_day"):
        return None
    if not is_new and not _limit_ok(user, "label_runs_per_day"):
        return None
    with st.status("Downloading reviews from Google Play…", expanded=True) as status:
        bar = st.progress(0.0, text="Starting…")

        def progress(kept, total, oldest, pages):
            reached = f" · reading reviews from {oldest:%d %b %Y}" if oldest else ""
            bar.progress(min(kept / max(total, 1), 1.0),
                         text=f"{kept:,} saved · {pages * 200:,} read{reached}")

        try:
            result = fetcher.collect(db(), app_id, lang=lang, country=country, count=count,
                                     added_by=user["email"], progress=progress, mode=mode,
                                     start=start, end=end, version=version)
        except Exception as e:  # noqa: BLE001
            repo.log_activity(db(), user["email"], "add_game" if is_new else "refresh", app_id,
                              status="error", details=str(e)[:300])
            status.update(label="Could not download reviews", state="error")
            st.error(f"{e}")
            return None
        repo.log_activity(db(), user["email"], "add_game" if result["is_new"] else "refresh",
                          app_id, n_items=result["added"],
                          details={"country": country, "lang": lang, "count": count, "mode": mode,
                                   "start": str(start or ""), "end": str(end or ""),
                                   "version": version or "", "pages": result["pages"],
                                   "stop": result["stop"]})
        refresh_caches()
        status.update(label=f"{result['game']['name']}: {result['added']:,} new reviews saved",
                      state="complete")
        if result["stop"] == "read limit reached":
            st.caption(f"Stopped after reading {result['pages'] * 200:,} reviews (back to "
                       f"{result['oldest']:%d %b %Y}). Google Play only lists reviews newest-first, so "
                       "for very popular games older dates are out of reach in one download.")
        elif result["stop"] == "version not found":
            st.caption("That version wasn't found – check the spelling on the game's Trends page.")
    return result


def run_insights(user: dict, app_ids: list[str], scheme_id: str) -> dict | None:
    if not _limit_ok(user, "label_runs_per_day"):
        return None
    with st.status("Writing the insight brief…", expanded=True) as status:
        llm = user_llm(user, log=status.write)
        if not llm:
            status.update(label="No API key", state="error")
            st.markdown(NO_KEY_MSG)
            return None
        try:
            answer = insights.generate(db(), app_ids, scheme_id, llm, user["email"])
        except (BadKey, QuotaExhausted, LLMError, ValueError) as e:
            repo.log_activity(db(), user["email"], "insights", status="error", details=str(e))
            status.update(label="Could not write insights", state="error")
            st.error(str(e))
            return None
        repo.log_activity(db(), user["email"], "insights", ",".join(app_ids)[:200],
                          n_calls=llm.calls)
        refresh_caches()
        status.update(label="Insights ready", state="complete")
    return answer
