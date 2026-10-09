#!/bin/bash
# One-time setup + first data run. Usage (from the project folder):
#   bash scripts/setup_mac.sh
# Everything printed is also saved to logs/setup.log.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
export PYTHONUNBUFFERED=1  # show progress lines immediately
exec > >(tee logs/setup.log) 2>&1

echo "== 1. Finding Python 3.10+ =="
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "No Python 3.10+ found. Install it from https://www.python.org/downloads/ and run again."
  exit 1
fi
echo "Using $PY ($($PY --version))"

echo "== 2. Virtual environment + packages =="
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt && echo "Packages installed."

echo "== 3. .env file =="
if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example"; fi
if grep -q '^GEMINI_API_KEY=.\+' .env; then echo "Gemini key found in .env"; else echo "Gemini key is EMPTY in .env"; fi

echo "== 4. Download reviews (Google Play) =="
python fetch_reviews.py

echo "== 5. LLM check =="
python llm_client.py || { echo "LLM check failed - see message above."; exit 1; }

echo "== 6. Test classification (50 reviews) =="
python classify_reviews.py --limit 50

echo "== SETUP FINISHED =="
