"""Central settings: paths, topic list and LLM settings.

Everything that might change (model names, topics, batch size) lives here,
so the rest of the code never needs editing for a config change.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "reviews.db"
GAMES_FILE = ROOT / "games.json"

load_dotenv(ROOT / ".env")


def _setting(name: str, default: str = "") -> str:
    """Read a setting from .env or the environment.

    Streamlit Community Cloud exposes app secrets as environment variables too,
    so the same code works locally and in the cloud. (The dashboard itself
    needs no keys at all - only the data scripts do.)
    """
    value = os.getenv(name)
    return value.strip() if value else default


# --- LLM -------------------------------------------------------------------
LLM_PROVIDER = _setting("LLM_PROVIDER", "gemini").lower()  # "gemini" or "groq"
GEMINI_API_KEY = _setting("GEMINI_API_KEY")
GEMINI_MODEL = _setting("GEMINI_MODEL", "gemini-3.8-flash")
# If the main model is overloaded (503) or has no free quota, try these in order.
GEMINI_FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
GROQ_API_KEY = _setting("GROQ_API_KEY")
GROQ_MODEL = _setting("GROQ_MODEL", "llama-3.3-70b-versatile")

BATCH_SIZE = 25                 # reviews per LLM call
MIN_SECONDS_BETWEEN_CALLS = 7   # stay under free-tier requests-per-minute limits
MAX_RETRIES = 6

# --- Classification labels -------------------------------------------------
SENTIMENTS = ["positive", "neutral", "negative"]

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


def load_games() -> dict:
    with open(GAMES_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_games(data: dict) -> None:
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
