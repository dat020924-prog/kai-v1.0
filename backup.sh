#!/bin/bash
# TradingView Project Backup Script
# Usage: ./backup.sh [message]
# Example: ./backup.sh "feat: add candlestick chart"

set -e

cd "$(dirname "$0")"

# Check for uncommitted changes
if [ -z "$(git status --porcelain)" ]; then
    echo "⚠️  No changes to commit. Working tree is clean."
    exit 1
fi

# Version format: vMAJOR.MINOR (auto-increment)
LATEST_TAG=$(git tag | grep -E '^v[0-9]+\.[0-9]+$' | sort -V | tail -1)
if [ -z "$LATEST_TAG" ]; then
    MAJOR=1
    MINOR=0
else
    MAJOR=$(echo "$LATEST_TAG" | cut -d. -f1 | tr -d 'v')
    MINOR=$(echo "$LATEST_TAG" | cut -d. -f2 | tr -d 'v')
    MINOR=$((MINOR + 1))
fi

VERSION="v${MAJOR}.${MINOR}"

# Commit message
if [ -z "$1" ]; then
    MSG="chore: backup to ${VERSION}"
else
    MSG="$1"
fi

echo "📦 Backing up to ${VERSION}..."
git add -A
git commit -m "${MSG}"
git tag -a "${VERSION}" -m "TradingView Lite ${VERSION}"

echo "✅ Backed up: ${VERSION}"
echo "   Commit: $(git rev-parse --short HEAD)"
echo "   Full log: git log --oneline"
