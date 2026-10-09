#!/bin/bash
# Fetch new reviews and label everything that is not labeled yet.
# Usage (from the project folder):  bash scripts/run_pipeline.sh
# Output is also saved to logs/pipeline.log (Claude reads progress from there).
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
export PYTHONUNBUFFERED=1
exec > >(tee logs/pipeline.log) 2>&1
source .venv/bin/activate

echo "== Fetch reviews ($(date '+%H:%M')) =="
python fetch_reviews.py

echo "== Classify reviews ($(date '+%H:%M')) =="
python classify_reviews.py

echo "== PIPELINE FINISHED ($(date '+%H:%M')) =="
