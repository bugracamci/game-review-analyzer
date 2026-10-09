"""Central settings for Game Review Radar.

Everything that might change (model names, topics, limits) lives here, so the
rest of the code never needs editing for a config change. Secrets are read
from .env locally and from environment variables / Streamlit secrets in the
cloud (Streamlit Community Cloud exposes root-level secrets as env vars).
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
LEGACY_DB_PATH = ROOT / "data" / "reviews.db"   # v1 snapshot (used by the migration script)
GAMES_FILE = ROOT / "games.json"

load_dotenv(ROOT / ".env")


def _setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value else default


APP_NAME = "Game Review Radar"
APP_TAGLINE = "Free competitor review analysis for small and indie game teams"
# Fallback base URL for share links (normally read from the browser request).
PUBLIC_URL = _setting("PUBLIC_URL", "https://game-review-analyzer.streamlit.app")

# --- Storage ------------------------------------------------------------------
# Local default: a SQLite file. Production: a Postgres URL (Supabase).
DATABASE_URL = _setting("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'radar.db'}")

# --- Accounts -----------------------------------------------------------------
ADMIN_EMAILS = {e.strip().lower() for e in _setting("ADMIN_EMAILS").split(",") if e.strip()}
# Encrypts users' saved API keys. Generate once with scripts/make_secrets.py.
ENCRYPTION_KEY = _setting("ENCRYPTION_KEY")
# Local testing only: pretend this email is logged in (never set this in the cloud).
DEV_LOGIN_EMAIL = _setting("DEV_LOGIN_EMAIL").lower()

# --- LLM ------------------------------------------------------------------------
# Server-side key: used by the CLI scripts and the weekly refresh job, never by users.
GEMINI_API_KEY = _setting("GEMINI_API_KEY")
GROQ_API_KEY = _setting("GROQ_API_KEY")

DEFAULT_PROVIDER = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"   # largest free quota in our tests
# If a model is overloaded (503) or out of free quota, try these in order.
GEMINI_FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-flash-latest",
                          "gemini-3.8-flash"]
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

DEFAULT_BATCH_SIZE = 50          # reviews per LLM call (fewer calls = more reviews per free quota)
MIN_SECONDS_BETWEEN_CALLS = 7    # stay under free-tier requests-per-minute limits
MAX_RETRIES = 6

# --- Data collection ------------------------------------------------------------
DEFAULT_REVIEWS_PER_GAME = 800
MAX_REVIEWS_PER_GAME = 2000
# (store country, review language, label)
MARKETS = [
    ("us", "en", "🇺🇸 United States (English)"),
    ("gb", "en", "🇬🇧 United Kingdom (English)"),
    ("tr", "tr", "🇹🇷 Türkiye (Turkish)"),
    ("de", "de", "🇩🇪 Germany (German)"),
    ("fr", "fr", "🇫🇷 France (French)"),
    ("br", "pt", "🇧🇷 Brazil (Portuguese)"),
    ("jp", "ja", "🇯🇵 Japan (Japanese)"),
    ("kr", "ko", "🇰🇷 South Korea (Korean)"),
]

# --- Default limits (admin can change them in the Admin page) -------------------
DEFAULT_LIMITS = {
    "new_games_per_day": 3,      # games a user can add to the catalog per day
    "label_runs_per_day": 10,    # labeling / insight runs per user per day
}

# --- Labels ---------------------------------------------------------------------
SENTIMENTS = ["positive", "neutral", "negative"]
DEFAULT_SCHEME_ID = "default"

# Fixed topic list -> results are comparable across games.
TOPICS = {
    "gameplay_fun": "Core gameplay & fun (what makes the game enjoyable or boring)",
    "monetization_ads": "Monetization & ads (prices, IAP, pay-to-win, ad frequency)",
    "difficulty_balance": "Difficulty & balance (too hard/easy, unfair, power creep)",
    "bugs_crashes": "Bugs & crashes (errors, lost progress, login problems)",
    "performance": "Performance (lag, FPS, battery, heat, loading times)",
    "controls_ui": "Controls & UI (joystick, menus, readability)",
    "content_progression": "Content & progression (variety, grind, updates, endgame)",
    "other": "Anything that does not fit the topics above",
}
TOPIC_LABELS = {
    "gameplay_fun": "Gameplay & fun",
    "monetization_ads": "Monetization & ads",
    "difficulty_balance": "Difficulty & balance",
    "bugs_crashes": "Bugs & crashes",
    "performance": "Performance",
    "controls_ui": "Controls & UI",
    "content_progression": "Content & progression",
    "other": "Other",
}

# --- Owner / community (admin can override in the Admin page) -------------------
DEFAULT_OWNER = {
    "owner_name": "Cengiz Buğra Camcı",
    "owner_role": "Mathematical engineer building tools for small game teams",
    "owner_github": "https://github.com/bugracamci",
    "owner_linkedin": "",
    "owner_email_public": "",
}
FEATURED_APP_IDS = ["com.dxx.firenow", "com.poncle.vampiresurvivors",
                    "com.brotato.shooting.survivors.action.roguelike", "com.xq.archeroii"]


def load_games() -> dict:
    """games.json: the seed list used by the CLI scripts and the weekly refresh."""
    with open(GAMES_FILE, encoding="utf-8") as f:
        return json.load(f)
