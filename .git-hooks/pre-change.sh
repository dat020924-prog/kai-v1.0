#!/bin/bash
# TradingView auto-backup hook
# Run BEFORE making any code changes
# Auto-detects changes → commits + tags

cd "$(dirname "$0")/.." || exit 1

# Check for uncommitted changes
if ! git diff --quiet 2>/dev/null && ! git ls-files --others --exclude-standard --quiet 2>/dev/null | grep -q .; then
  echo "✅ No changes detected — skip backup."
  exit 0
fi

# Commit all changes
git add -A
git commit -m "pre-change backup $(date '+%Y-%m-%d %H:%M:%S')"

# Get next tag number
LAST_TAG=$(git tag -l 'v*' | sort -V | tail -1)
if [[ -z "$LAST_TAG" ]]; then
  NEXT_NUM=0
else
  NEXT_NUM=$((10#${LAST_TAG#v} + 1))
fi
NEXT_TAG="v${NEXT_NUM}"
git tag "$NEXT_TAG"

echo "✅ Backed up as $NEXT_TAG"
