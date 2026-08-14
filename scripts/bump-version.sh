#!/bin/bash
#
# Bump loom-ai version using FlossWare X.Y format.
#
# Usage:
#   scripts/bump-version.sh minor     # 1.0 -> 1.1
#   scripts/bump-version.sh major     # 1.1 -> 2.0
#   scripts/bump-version.sh 3.5       # Set explicitly
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYPROJECT="$PROJECT_ROOT/pyproject.toml"
INIT_PY="$PROJECT_ROOT/loom_ai/__init__.py"
SERVER_PY="$PROJECT_ROOT/loom_ai/server.py"

current_version() {
    grep -oP '(?<=^version = ")[0-9]+\.[0-9]+' "$PYPROJECT"
}

CURRENT=$(current_version)
MAJOR="${CURRENT%%.*}"
MINOR="${CURRENT##*.}"

case "${1:-}" in
    minor)
        NEW_VERSION="${MAJOR}.$((MINOR + 1))"
        ;;
    major)
        NEW_VERSION="$((MAJOR + 1)).0"
        ;;
    [0-9]*.[0-9]*)
        if ! echo "$1" | grep -qP '^\d+\.\d+$'; then
            echo "Error: Version must be in X.Y format (e.g. 2.0), got: $1"
            exit 1
        fi
        NEW_VERSION="$1"
        ;;
    *)
        echo "Usage: $0 {minor|major|X.Y}"
        echo ""
        echo "  minor   Bump minor version ($CURRENT -> ${MAJOR}.$((MINOR + 1)))"
        echo "  major   Bump major version ($CURRENT -> $((MAJOR + 1)).0)"
        echo "  X.Y     Set exact version (FlossWare X.Y format only)"
        echo ""
        echo "Current version: $CURRENT"
        exit 1
        ;;
esac

if [ "$NEW_VERSION" = "$CURRENT" ]; then
    echo "Version is already $CURRENT"
    exit 0
fi

echo "Bumping version: $CURRENT -> $NEW_VERSION"

sed -i "s/^version = \"${CURRENT}\"/version = \"${NEW_VERSION}\"/" "$PYPROJECT"

sed -i "s/__version__ = \"${CURRENT}\"/__version__ = \"${NEW_VERSION}\"/" "$INIT_PY"

if [ -f "$SERVER_PY" ]; then
    sed -i "s/version=\"${CURRENT}\"/version=\"${NEW_VERSION}\"/" "$SERVER_PY"
fi

echo "Updated files:"
echo "  $PYPROJECT"
echo "  $INIT_PY"
[ -f "$SERVER_PY" ] && echo "  $SERVER_PY"
echo ""
echo "Version is now: $NEW_VERSION"
