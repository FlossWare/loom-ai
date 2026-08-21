#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "${LOOM_CANARY:-1}" == 1 ]] || { echo 'Refusing dogfood: LOOM_CANARY must be 1.' >&2; exit 1; }
./scripts/doctor.sh
PY=.venv/bin/python
[[ -x "$PY" ]] || PY=python3
exec "$PY" -m loom_ai.acceptance "$@"
