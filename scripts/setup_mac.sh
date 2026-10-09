#!/bin/bash
# One-time setup on a Mac: Python virtual environment + packages + .env file.
# Usage (from the project folder):  bash scripts/setup_mac.sh
cd "$(dirname "$0")/.." || exit 1
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "Install Python 3.10+ from https://www.python.org/downloads/"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt && echo "Packages installed."
[ -f .env ] || { cp .env.example .env; echo "Created .env - fill in your keys."; }
