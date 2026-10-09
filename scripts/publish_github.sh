#!/bin/bash
# Publish this project to a public GitHub repository (safe to run again for updates).
# Usage (from the project folder):  bash scripts/publish_github.sh
cd "$(dirname "$0")/.." || exit 1
REPO_NAME="game-review-analyzer"
export GIT_PAGER=cat GH_PAGER=cat

echo "== 1. Tools =="
command -v git >/dev/null || { echo "git missing: run 'xcode-select --install' and try again."; exit 1; }
if ! command -v gh >/dev/null; then
  if command -v brew >/dev/null; then
    echo "Installing GitHub CLI (gh) with Homebrew..."; brew install gh || exit 1
  else
    echo "GitHub CLI missing. Install it from https://cli.github.com and run this script again."; exit 1
  fi
fi

echo "== 2. GitHub login =="
gh auth status >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol https --web || exit 1
if [ -d .github/workflows ] && ! gh auth status 2>&1 | grep -q "workflow"; then
  echo "GitHub needs one extra permission to upload the weekly automation (workflow files)."
  gh auth refresh -h github.com -s workflow || exit 1
fi
gh auth setup-git >/dev/null 2>&1   # lets git push with the gh login
LOGIN=$(gh api user -q .login) || exit 1
GH_ID=$(gh api user -q .id)
NAME=$(gh api user -q '.name // empty'); [ -n "$NAME" ] || NAME="$LOGIN"
# GitHub's private "noreply" address: commits are linked to you without exposing your email.
EMAIL="${GH_ID}+${LOGIN}@users.noreply.github.com"
echo "Logged in as $LOGIN"

echo "== 3. Local git repository =="
[ -d .git ] || git init -q -b main
git config user.name "$NAME"      # only for this project, not global
git config user.email "$EMAIL"
git add -A

echo "== 4. Safety check: no secrets in the commit =="
if git diff --cached --name-only | grep -qE '(^|/)\.env$|secrets.*\.toml'; then
  echo "STOP: a secrets file is staged. Nothing was published."; exit 1
fi
# (this script itself contains the patterns below, so it is excluded from the scan)
if git diff --cached -U0 -- . ':(exclude)scripts/publish_github.sh' | grep -E '^\+' | grep -qE 'AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z]{20,}|GOCSPX-|postgres(ql)?://[^:]+:[^@]+@'; then
  echo "STOP: something that looks like an API key is staged. Nothing was published."; exit 1
fi
echo "OK - $(git diff --cached --name-only | wc -l | tr -d ' ') files staged, no secrets found."

echo "== 5. Commit =="
if git diff --cached --quiet; then
  echo "(no new changes to commit)"
else
  git commit -q -m "Mobile Game Review Analyzer: LLM-labeled Google Play reviews + Streamlit dashboard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LCPn85bmg1eYgNHRzJBVTL" || exit 1
fi
git rev-parse HEAD >/dev/null 2>&1 || { echo "No commit exists - stopping."; exit 1; }

echo "== 6. Push to GitHub =="
if ! git remote get-url origin >/dev/null 2>&1; then
  if gh repo view "$LOGIN/$REPO_NAME" >/dev/null 2>&1; then
    git remote add origin "https://github.com/$LOGIN/$REPO_NAME.git"
  else
    gh repo create "$REPO_NAME" --public \
      --description "LLM-powered review analysis of competing mobile games (Gemini + Streamlit)" || exit 1
    git remote add origin "https://github.com/$LOGIN/$REPO_NAME.git"
  fi
fi
git push -u origin main || exit 1
echo "== PUBLISHED: https://github.com/$LOGIN/$REPO_NAME =="
