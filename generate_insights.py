"""Command line: write the LiveOps / UA brief for the featured comparison.

Usage:  python generate_insights.py
"""
import config
from core import insights
from core.db import get_db
from core.llm import LLMConfig


def main():
    if not config.GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY is missing in .env")
    answer = insights.generate(get_db(), config.FEATURED_APP_IDS, config.DEFAULT_SCHEME_ID,
                               LLMConfig(api_key=config.GEMINI_API_KEY), user_email="cli")
    print("Saved. Headline:", answer.get("headline"))


if __name__ == "__main__":
    main()
