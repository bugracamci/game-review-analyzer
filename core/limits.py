"""Daily usage limits per user, so one account can't overload the shared catalog.

Admins have no limits. The numbers can be changed on the Admin page.
"""
import config
from core import repo
from core.db import Database

ACTIONS = {
    "new_games_per_day": ["add_game"],
    "label_runs_per_day": ["label", "insights", "refresh"],
}


def get_limits(db: Database) -> dict:
    return {**config.DEFAULT_LIMITS, **(repo.get_setting(db, "limits", {}) or {})}


def check(db: Database, email: str, limit_name: str, is_admin: bool = False) -> tuple[bool, int]:
    """Returns (allowed, remaining today)."""
    if is_admin:
        return True, 999
    allowed = int(get_limits(db)[limit_name])
    used = repo.count_activity(db, email, ACTIONS[limit_name])
    return used < allowed, max(allowed - used, 0)
