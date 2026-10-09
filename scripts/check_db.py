"""Quick check: can we reach the database in DATABASE_URL, and what's inside?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core import repo  # noqa: E402
from core.db import get_db  # noqa: E402

db = get_db()
print("Database type:", db.kind, "| host:", config.DATABASE_URL.split("@")[-1].split("/")[0])
print("Contents:", repo.stats(db))
