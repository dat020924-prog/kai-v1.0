#!/bin/bash
# Pre-change backup hook — gọi script này TRƯỚC mỗi lần sửa code
# Tự động backup nếu có thay đổi chưa commit

set -e

cd "$(dirname "$0")/.."

# Check for uncommitted changes
CHANGES=$(git status --porcelain)
if [ -z "$CHANGES" ]; then
    echo "✅ Working tree clean — no backup needed."
    exit 0
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

# Auto commit message
MSG="chore: auto-backup to ${VERSION} before change"

echo "📦 Auto-backup → ${VERSION}"
git add -A
git commit -m "${MSG}"
git tag -a "${VERSION}" -m "TradingView Lite ${VERSION}"

echo "✅ Backed up: ${VERSION} (commit: $(git rev-parse --short HEAD))"
