"""Small helpers shared by the core modules."""
import uuid
from datetime import datetime, timedelta, timezone


def now() -> str:
    """Current UTC time as an ISO string (sortable, works in SQLite and Postgres)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex
