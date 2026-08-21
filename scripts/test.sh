#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY=.venv/bin/python
[[ -x "$PY" ]] || PY=python3
exec "$PY" -m pytest -q "$@"
