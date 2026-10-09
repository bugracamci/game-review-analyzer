#!/bin/bash
# One-off: remove the "Co-Authored-By" / "Claude-Session" lines from every commit
# message, then force-push the cleaned history to GitHub.
# Usage (from the project folder):  bash scripts/clean_commit_history.sh
cd "$(dirname "$0")/.." || exit 1
export GIT_PAGER=cat FILTER_BRANCH_SQUELCH_WARNING=1
rm -f .git/index.lock

echo "== 1. Save the latest change (publish script without co-author lines) =="
git add -A
git diff --cached --quiet || git commit -q -m "Publish script: plain commit messages" || exit 1
if [ -n "$(git status --porcelain)" ]; then
  echo "STOP: there are uncommitted changes. Nothing was changed."; exit 1
fi

echo "== 2. Backup =="
BACKUP="backup-before-clean-$(date +%Y%m%d-%H%M%S)"
git branch "$BACKUP" && echo "Backup branch (local only): $BACKUP"

echo "== 3. Rewrite commit messages =="
git filter-branch -f --msg-filter \
  "sed -e '/^Co-Authored-By: Claude/d' -e '/^Claude-Session:/d' | perl -0pe 's/\s+\z/\n/'" \
  -- main || exit 1
rm -rf .git/refs/original

LEFT=$(git log main --format=%B | grep -c -E '^(Co-Authored-By: Claude|Claude-Session:)')
echo "Co-author lines left: $LEFT"
[ "$LEFT" = "0" ] || { echo "STOP: some lines were not removed. Nothing was pushed."; exit 1; }

echo "== 4. Push to GitHub (replaces the old history) =="
gh auth setup-git >/dev/null 2>&1
git push --force-with-lease origin main || exit 1
echo ""
echo "Done. GitHub's 'Contributors' box can take a few hours to refresh."
