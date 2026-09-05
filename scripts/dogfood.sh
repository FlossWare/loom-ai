#!/usr/bin/env bash
set -euo pipefail

# Loom dogfood / release qualification.
# Local checkout: ./scripts/dogfood.sh
# Remote clean-machine run:
#   curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash

REPO_URL="https://github.com/FlossWare/loom-ai.git"
REF="${LOOM_DOGFOOD_REF:-main}"
KEEP="${LOOM_DOGFOOD_KEEP:-0}"

log() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nFAIL: %s\n' "$*" >&2; exit 1; }

# A curl | bash invocation has no repository checkout. Bootstrap a clean
# checkout, then execute the repository copy so all paths and helpers resolve.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    command -v git >/dev/null 2>&1 || fail "git is required for a remote dogfood run"
    WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/loom-dogfood.XXXXXX")"
    trap 'if [[ "$KEEP" != "1" ]]; then rm -rf "$WORKDIR"; fi' EXIT
    ROOT="$WORKDIR/loom-ai"
    log "Cloning $REPO_URL@$REF"
    git clone --quiet --depth 1 --branch "$REF" "$REPO_URL" "$ROOT" || fail "unable to clone Loom"
    exec env LOOM_DOGFOOD_REF="$REF" LOOM_DOGFOOD_KEEP="$KEEP" "$ROOT/scripts/dogfood.sh" "$@"
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

[[ "${LOOM_CANARY:-1}" == 1 ]] || fail "Refusing dogfood: LOOM_CANARY must be 1."

log "Loom dogfood"
printf 'Commit: %s\n' "$(git rev-parse HEAD)"
printf 'Python: %s\n' "$(python3 --version 2>&1)"
printf 'OS: %s\n' "$(uname -srm)"

log "Environment preflight"
./scripts/doctor.sh

log "Acceptance harness"
PY=.venv/bin/python
[[ -x "$PY" ]] || PY=python3
"$PY" -m loom_ai.acceptance "$@"

log "Static quality"
if command -v ruff >/dev/null 2>&1; then
    ruff format --check .
    ruff check .
else
    echo "WARN: ruff is not installed; skipping static quality checks" >&2
fi

log "Full automated test suite"
"$PY" -m pytest -q

log "Package build"
if "$PY" -m build --version >/dev/null 2>&1; then
    "$PY" -m build --wheel --sdist
else
    echo "WARN: Python build module is not installed; skipping package build" >&2
fi

echo
printf 'RESULT: LOOM DOGFOOD PASSED\n'
