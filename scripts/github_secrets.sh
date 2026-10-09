#!/bin/bash
# Copy DATABASE_URL and GEMINI_API_KEY from .env into the GitHub repository's
# Actions secrets (encrypted by GitHub), for the weekly refresh job.
# Usage (from the project folder):  bash scripts/github_secrets.sh
cd "$(dirname "$0")/.." || exit 1
for name in DATABASE_URL GEMINI_API_KEY; do
  value=$(grep "^$name=" .env | head -1 | cut -d= -f2-)
  if [ -z "$value" ]; then echo "$name is empty in .env - skipped"; continue; fi
  printf '%s' "$value" | gh secret set "$name" && echo "Saved $name to GitHub Actions secrets"
done
