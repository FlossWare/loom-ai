#!/usr/bin/env bash
set -euo pipefail

# Loom dogfood / release qualification.
# Baseline clean-machine run:
#   curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | bash
# Full live dogfood (provider/infrastructure required):
#   curl -fsSL https://raw.githubusercontent.com/FlossWare/loom-ai/main/scripts/dogfood.sh | LOOM_DOGFOOD_LIVE=1 bash
# Local checkout: ./scripts/dogfood.sh

REPO_URL="https://github.com/FlossWare/loom-ai.git"
REF="${LOOM_DOGFOOD_REF:-main}"
KEEP="${LOOM_DOGFOOD_KEEP:-0}"
LIVE="${LOOM_DOGFOOD_LIVE:-0}"

log() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nFAIL: %s\n' "$*" >&2; exit 1; }

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    command -v git >/dev/null 2>&1 || fail "git is required for a remote dogfood run"
    WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/loom-dogfood.XXXXXX")"
    trap 'if [[ "$KEEP" != "1" ]]; then rm -rf "$WORKDIR"; fi' EXIT
    ROOT="$WORKDIR/loom-ai"
    log "Cloning $REPO_URL@$REF"
    git clone --quiet --depth 1 --branch "$REF" "$REPO_URL" "$ROOT" || fail "unable to clone Loom"
    exec env LOOM_DOGFOOD_REF="$REF" LOOM_DOGFOOD_KEEP="$KEEP" LOOM_DOGFOOD_LIVE="$LIVE" "$ROOT/scripts/dogfood.sh" "$@"
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

[[ "${LOOM_CANARY:-1}" == 1 ]] || fail "Refusing dogfood: LOOM_CANARY must be 1."
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || fail "Python 3.11+ is required"

log "Loom qualification"
printf 'Commit: %s\n' "$(git rev-parse HEAD)"
printf 'Python: %s\n' "$(python3 --version 2>&1)"
printf 'OS: %s\n' "$(uname -srm)"

if [[ ! -x .venv/bin/python ]]; then
    log "Creating isolated virtual environment"
    python3 -m venv .venv
fi
PY=.venv/bin/python

log "Installing qualification dependencies"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -e '.[dev]'
"$PY" -m pip install --quiet build

log "Static quality"
"$PY" -m ruff format --check .
"$PY" -m ruff check .

log "Full automated test suite"
"$PY" -m pytest -q

log "Package build"
"$PY" -m build --wheel --sdist

if [[ "$LIVE" == 1 ]]; then
    log "Live environment preflight"
    ./scripts/doctor.sh

    log "Acceptance harness"
    "$PY" -m loom_ai.acceptance "$@"
else
    log "Live dogfood"
    echo "Baseline qualification passed. Live provider/infrastructure checks were not run."
    echo "Run with LOOM_DOGFOOD_LIVE=1 for doctor + acceptance checks."
fi

echo
if [[ "$LIVE" == 1 ]]; then
    printf 'RESULT: LOOM LIVE DOGFOOD PASSED\n'
else
    printf 'RESULT: LOOM BASELINE QUALIFICATION PASSED\n'
fi
