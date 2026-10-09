#!/bin/bash
# Quality check + LLM insights, then open the dashboard.
# Usage (from the project folder):  bash scripts/insights_and_dashboard.sh
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
export PYTHONUNBUFFERED=1
source .venv/bin/activate
{
  echo "== Label any leftover reviews =="
  python classify_reviews.py
  echo "== Model agreement check (100 reviews) =="
  python scripts/agreement_check.py --model gemini-3.1-flash-lite
  echo "== Generate insights =="
  python generate_insights.py
  echo "== DONE - starting dashboard =="
} 2>&1 | tee logs/insights.log

streamlit run app.py
