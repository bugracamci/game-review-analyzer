#!/bin/bash
# Run the app locally. With --dev, you are "signed in" as the first ADMIN_EMAILS address
# without Google (for testing only). Usage: bash scripts/dev_run.sh [--dev]
cd "$(dirname "$0")/.." || exit 1
source .venv/bin/activate
if [ "$1" == "--dev" ]; then
  export DEV_LOGIN_EMAIL=$(grep '^ADMIN_EMAILS=' .env | cut -d= -f2 | cut -d, -f1)
  echo "Dev login as: ${DEV_LOGIN_EMAIL:-(none - set ADMIN_EMAILS in .env)}"
fi
mkdir -p logs
streamlit run app.py 2>&1 | tee logs/app.log
