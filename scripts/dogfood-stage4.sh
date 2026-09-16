#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PY=${PYTHON:-python3}

"$PY" -m pip install -e '.[dev,server]' >/dev/null
"$PY" -m ruff format --check .
"$PY" -m ruff check .
"$PY" -m pytest -q

printf '%s\n' 'RESULT: LOOM STAGE 4 DOGFOOD BASELINE PASSED'
